from __future__ import annotations

import asyncio
import re
from datetime import datetime, timedelta, timezone

import httpx

from app.providers.base import ProviderError, SourceProvider
from app.providers.util import make_signal_id, parse_datetime, sort_timestamp, strip_html
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal

try:  # feedparser is a mature, pure-Python RSS/Atom parser.
    import feedparser
except ImportError:  # pragma: no cover - exercised only in minimal installs
    feedparser = None

USER_AGENT = "OpportunityScout/0.1 (+local research tool; RSS reader)"
MAX_FEED_BYTES = 5 * 1024 * 1024


class RssProvider(SourceProvider):
    """RSS / Atom adapter backed by feedparser.

    Feeds are user-supplied through ``OPPORTUNITY_RSS_FEEDS``. The adapter never
    scrapes HTML pages; it only reads the feed documents the user asked for.
    """

    def __init__(
        self,
        feeds: tuple[str, ...] | list[str],
        timeout: float = 25.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.feeds = tuple(dict.fromkeys(feed.strip() for feed in feeds if feed.strip()))
        self.timeout = timeout
        self.transport = transport
        available = feedparser is not None and bool(self.feeds)
        self.info = ProviderInfo(
            id="rss",
            name="RSS / 博客",
            group="news",
            capabilities=["search", "read"],
            auth="none",
            status="ready" if available else "not_configured",
            cost="free",
            rate_limit={"requests": 20, "window_seconds": 60},
            note=(
                f"feedparser · {len(self.feeds)} 个订阅源"
                if available
                else "设置 OPPORTUNITY_RSS_FEEDS 后启用"
            ),
        )

    async def health(self) -> ProviderHealth:
        if feedparser is None:
            return ProviderHealth(
                id=self.info.id,
                status="not_configured",
                detail="未安装 feedparser，请执行 pip install -r requirements.txt。",
            )
        if not self.feeds:
            return ProviderHealth(
                id=self.info.id,
                status="not_configured",
                detail="未配置 RSS 订阅源：OPPORTUNITY_RSS_FEEDS",
            )
        return ProviderHealth(
            id=self.info.id,
            status="ready",
            detail=f"{len(self.feeds)} 个订阅源",
        )

    async def search(self, query: SearchQuery) -> list[Signal]:
        if feedparser is None:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "未安装 feedparser。",
                "执行 pip install -r requirements.txt。",
            )
        if not self.feeds:
            raise ProviderError(
                "PROVIDER_NOT_CONFIGURED",
                "未配置 RSS 订阅源。",
                "设置 OPPORTUNITY_RSS_FEEDS，多个地址用逗号分隔。",
            )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            transport=self.transport,
            headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*"},
        ) as client:
            results = await asyncio.gather(
                *(self._fetch_feed(client, feed) for feed in self.feeds),
                return_exceptions=True,
            )

        signals: list[Signal] = []
        errors: list[BaseException] = []
        for feed, result in zip(self.feeds, results):
            if isinstance(result, BaseException):
                errors.append(result)
                continue
            signals.extend(result)

        if not signals and errors:
            first = errors[0]
            if isinstance(first, ProviderError):
                raise first
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"所有 RSS 订阅源都读取失败：{first}",
            )

        deduped: dict[str, Signal] = {signal.id: signal for signal in signals}
        ordered = sorted(
            deduped.values(),
            key=lambda signal: sort_timestamp(signal.published_at),
            reverse=True,
        )
        if query.time_range_days:
            cutoff = datetime.now(timezone.utc) - timedelta(days=query.time_range_days)
            filtered: list[Signal] = []
            for signal in ordered:
                published = parse_datetime(signal.published_at)
                # Entries without a parseable date are kept rather than silently dropped.
                if published is None or published >= cutoff:
                    filtered.append(signal)
            ordered = filtered

        terms = self._search_terms(query)
        if terms:
            ordered = [
                signal
                for signal in ordered
                if any(
                    term in f"{signal.title} {signal.quote}".lower()
                    for term in terms
                )
            ]
        return ordered[: query.limit]

    @staticmethod
    def _search_terms(query: SearchQuery) -> list[str]:
        raw = " ".join([query.text, *query.keywords]).lower()
        terms = [word for word in re.findall(r"[0-9a-z]+", raw) if len(word) >= 3]
        terms.extend(
            term
            for term in re.findall(r"[一-鿿]{2,}", raw)
            if term not in terms
        )
        return list(dict.fromkeys(terms))

    async def _fetch_feed(
        self,
        client: httpx.AsyncClient,
        feed_url: str,
    ) -> list[Signal]:
        try:
            response = await client.get(feed_url)
        except httpx.TimeoutException as exc:
            raise ProviderError(
                "PROVIDER_TIMEOUT",
                f"RSS 读取超时：{feed_url}",
                "稍后重试；不要循环重试。",
            ) from exc
        except httpx.HTTPError as exc:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"RSS 读取失败：{feed_url}（{exc}）",
            ) from exc

        if response.status_code == 429:
            raise ProviderError(
                "PROVIDER_RATE_LIMITED",
                f"RSS 源限流：{feed_url}",
                "稍后重试。",
                retry_after_seconds=60,
            )
        if response.status_code >= 400:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"RSS 源返回 HTTP {response.status_code}：{feed_url}",
            )
        if len(response.content) > MAX_FEED_BYTES:
            raise ProviderError(
                "PROVIDER_BAD_OUTPUT",
                f"RSS 内容超过 {MAX_FEED_BYTES // 1024 // 1024}MB：{feed_url}",
            )

        parsed = feedparser.parse(response.content)
        entries = getattr(parsed, "entries", None) or []
        if not entries and getattr(parsed, "bozo", False):
            raise ProviderError(
                "PROVIDER_BAD_OUTPUT",
                f"RSS 解析失败：{feed_url}",
                str(getattr(parsed, "bozo_exception", ""))[:300],
            )

        feed_title = ""
        feed = getattr(parsed, "feed", None)
        if feed:
            feed_title = str(feed.get("title") or "")
        feed_title = feed_title or feed_url
        signals: list[Signal] = []
        for entry in entries:
            url = str(entry.get("link") or "").strip()
            title = strip_html(entry.get("title") or "", 300)
            if not url or not title:
                continue
            quote = strip_html(
                entry.get("summary")
                or entry.get("description")
                or self._content_value(entry),
                2000,
            )
            published = entry.get("published") or entry.get("updated")
            tags = [
                str(tag.get("term"))
                for tag in (entry.get("tags") or [])
                if isinstance(tag, dict) and tag.get("term")
            ]
            signals.append(
                Signal(
                    id=make_signal_id(self.info.id, url, title),
                    provider_id=self.info.id,
                    source_type="article",
                    source_url=url,
                    title=title,
                    quote=quote,
                    author_public=entry.get("author"),
                    published_at=str(published) if published else None,
                    metrics={
                        "feed": feed_title,
                        "feed_url": feed_url,
                        "tags": tags[:8],
                    },
                    raw={"feed_url": feed_url},
                )
            )
        return signals

    @staticmethod
    def _content_value(entry: dict) -> str:
        content = entry.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict):
                return str(first.get("value") or "")
        return ""
