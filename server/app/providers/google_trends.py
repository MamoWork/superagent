from __future__ import annotations

import asyncio
import re
import warnings
from urllib.parse import quote

from app.providers.base import ProviderError, SourceProvider
from app.providers.util import make_signal_id
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal

try:  # pytrends is the de-facto OSS client for the public Google Trends endpoint.
    from pytrends.exceptions import ResponseError, TooManyRequestsError
    from pytrends.request import TrendReq
except ImportError:  # pragma: no cover - exercised only in minimal installs
    TrendReq = None
    ResponseError = Exception
    TooManyRequestsError = Exception


_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "at", "is",
    "are", "be", "with", "about", "how", "what", "why", "who", "can", "could",
    "should", "would", "do", "does", "my", "our", "your", "their", "i", "we",
    "you", "it", "this", "that", "there", "from", "by", "as", "into", "using",
}


class GoogleTrendsProvider(SourceProvider):
    """Google Trends adapter backed by pytrends.

    This uses the public Trends endpoint, which is undocumented and may rate
    limit or change. Failures are normalized; the adapter never retries in a
    loop.
    """

    def __init__(
        self,
        geo: str = "US",
        timeout: float = 30.0,
    ) -> None:
        self.geo = geo.strip().upper()
        self.timeout = timeout
        available = TrendReq is not None
        self.info = ProviderInfo(
            id="google.trends",
            name="Google Trends",
            group="trends",
            capabilities=["trends", "search"],
            auth="none",
            status="ready" if available else "not_configured",
            cost="free",
            rate_limit={"requests": 5, "window_seconds": 60},
            note="pytrends · 非官方公开接口，可能限流或暂时不可用。",
        )

    async def health(self) -> ProviderHealth:
        if TrendReq is None:
            return ProviderHealth(
                id=self.info.id,
                status="not_configured",
                detail="未安装 pytrends，请执行 pip install -r requirements.txt。",
            )
        return ProviderHealth(
            id=self.info.id,
            status="ready",
            detail=f"地区 {self.geo or '全球'}（仅检查依赖，不发起 Google 请求）",
        )

    async def search(self, query: SearchQuery) -> list[Signal]:
        if TrendReq is None:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "未安装 pytrends。",
                "执行 pip install -r requirements.txt。",
            )
        keyword = self._keyword(query)
        timeframe = self._timeframe(query.time_range_days)
        try:
            signals = await asyncio.wait_for(
                asyncio.to_thread(self._sync_search, keyword, timeframe, query.limit),
                timeout=self.timeout + 15,
            )
        except asyncio.TimeoutError as exc:
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                f"Google Trends 查询超过 {self.timeout:.0f} 秒。",
                "稍后重试；不要循环重试。",
            ) from exc
        if not signals:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"Google Trends 没有返回与「{keyword}」相关的数据。",
                "换一个更短的关键词，或稍后再试。",
            )
        return signals[: query.limit]

    @staticmethod
    def _keyword(query: SearchQuery) -> str:
        if query.keywords:
            return " ".join(str(query.keywords[0]).split())[:100]
        words = re.findall(r"[0-9a-zA-Z]+", query.text.lower())
        words = [
            word
            for word in words
            if len(word) > 1 and word not in _STOPWORDS
        ]
        # Trends needs a short search phrase; a full direction sentence rarely
        # has volume data.
        compact = " ".join(words[:2])
        return compact[:100] or " ".join(query.text.split())[:40]

    @staticmethod
    def _timeframe(days: int | None) -> str:
        if not days or days <= 30:
            return "today 1-m"
        if days <= 90:
            return "today 3-m"
        if days <= 365:
            return "today 12-m"
        return "today 5-y"

    def _sync_search(self, keyword: str, timeframe: str, limit: int) -> list[Signal]:
        client = TrendReq(hl="en-US", tz=0, timeout=(10, self.timeout))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", FutureWarning)
                client.build_payload([keyword], timeframe=timeframe, geo=self.geo or "")
                interest = client.interest_over_time()
                try:
                    related_map = client.related_queries() or {}
                except TooManyRequestsError:
                    raise
                except Exception:
                    # Related queries often fail independently; interest data
                    # is still useful evidence.
                    related_map = {}
        except TooManyRequestsError as exc:
            raise ProviderError(
                "PROVIDER_RATE_LIMITED",
                "Google Trends 限流。",
                "稍后重试，不要换后端反复请求。",
                retry_after_seconds=120,
            ) from exc
        except ResponseError as exc:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"Google Trends 返回错误：{exc}",
                "Google 可能临时限制了该接口；稍后再试。",
            ) from exc
        except Exception as exc:  # network/schema changes from the undocumented endpoint
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"Google Trends 查询失败：{exc}",
                "稍后重试；不要循环重试。",
            ) from exc

        explore_url = (
            "https://trends.google.com/trends/explore"
            f"?date={quote(timeframe)}&geo={quote(self.geo or '')}&q={quote(keyword)}"
        )
        signals: list[Signal] = []

        if interest is not None and not interest.empty and keyword in interest.columns:
            series = interest[keyword].dropna()
            if not series.empty:
                average = round(float(series.mean()))
                peak = int(series.max())
                signals.append(
                    Signal(
                        id=make_signal_id(self.info.id, explore_url, f"interest:{keyword}"),
                        provider_id=self.info.id,
                        source_type="trend",
                        source_url=explore_url,
                        title=f"Google Trends 搜索热度：{keyword}",
                        quote=(
                            f"{self._label(timeframe)}平均热度 {average}/100，"
                            f"峰值 {peak}/100（地区 {self.geo or '全球'}）。"
                        ),
                        metrics={
                            "kind": "interest_over_time",
                            "keyword": keyword,
                            "average": average,
                            "peak": peak,
                            "geo": self.geo,
                            "timeframe": timeframe,
                        },
                    )
                )

        related = related_map.get(keyword) if isinstance(related_map, dict) else None
        seen_terms: set[str] = set()
        if isinstance(related, dict):
            for kind in ("top", "rising"):
                table = related.get(kind)
                if table is None or getattr(table, "empty", True):
                    continue
                per_kind = max(1, (limit - len(signals)) // 2) if kind == "top" else max(1, limit - len(signals))
                for _, row in table.head(per_kind).iterrows():
                    term = str(row.get("query") or "").strip()
                    if not term:
                        continue
                    # pytrends' rising table occasionally contains unrelated
                    # noise; keep terms that share a token with the keyword.
                    if kind == "rising" and not self._relevant(term, keyword):
                        continue
                    key = term.casefold()
                    if key in seen_terms:
                        continue
                    seen_terms.add(key)
                    value = int(row.get("value") or 0)
                    metric_label = "热度" if kind == "top" else "热度增幅"
                    signals.append(
                        Signal(
                            id=make_signal_id(
                                self.info.id,
                                explore_url,
                                f"{kind}:{term}",
                            ),
                            provider_id=self.info.id,
                            source_type="trend",
                            source_url=explore_url,
                            title=f"Google Trends {('热门' if kind == 'top' else '上升')}查询：{term}",
                            quote=(
                                f"与「{keyword}」相关，{metric_label} {value}。"
                                "可作为选品或内容方向的辅助信号。"
                            ),
                            metrics={
                                "kind": f"related_{kind}",
                                "keyword": keyword,
                                "query": term,
                                "value": value,
                                "geo": self.geo,
                                "timeframe": timeframe,
                            },
                        )
                    )
        return signals

    @staticmethod
    def _relevant(term: str, keyword: str) -> bool:
        tokens = [
            token
            for token in re.split(r"[^0-9a-zA-Z一-鿿]+", keyword.lower())
            if len(token) >= 3
        ]
        if not tokens:
            return True
        lowered = term.lower()
        return any(token in lowered for token in tokens)

    @staticmethod
    def _label(timeframe: str) -> str:
        return {
            "today 1-m": "近 1 个月",
            "today 3-m": "近 3 个月",
            "today 12-m": "近 1 年",
            "today 5-y": "近 5 年",
        }.get(timeframe, timeframe)
