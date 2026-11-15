from __future__ import annotations

import time

import httpx

from app.providers.base import ProviderError, SourceProvider
from app.providers.util import make_signal_id, strip_html
from app.schemas import ProviderHealth, ProviderInfo, SearchQuery, Signal

SEARCH_URL = "https://hn.algolia.com/api/v1/search"


class HackerNewsProvider(SourceProvider):
    """Hacker News search through the public Algolia HN API."""

    def __init__(
        self,
        timeout: float = 20.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.transport = transport
        self.info = ProviderInfo(
            id="hackernews",
            name="Hacker News",
            group="community",
            capabilities=["search"],
            auth="none",
            status="ready",
            cost="free",
            rate_limit={"requests": 30, "window_seconds": 60},
            note="Algolia HN Search API · 只读公开数据。",
        )

    async def health(self) -> ProviderHealth:
        return ProviderHealth(id=self.info.id, status="ready", detail=SEARCH_URL)

    async def search(self, query: SearchQuery) -> list[Signal]:
        params: dict[str, object] = {
            "query": query.text,
            "tags": "story",
            "hitsPerPage": min(query.limit, 50),
        }
        if query.time_range_days:
            params["numericFilters"] = (
                f"created_at_i>{int(time.time()) - query.time_range_days * 86400}"
            )

        async with httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            transport=self.transport,
            headers={"User-Agent": "OpportunityScout/0.1"},
        ) as client:
            try:
                response = await client.get(SEARCH_URL, params=params)
            except httpx.TimeoutException as exc:
                raise ProviderError(
                    "PROVIDER_TIMEOUT",
                    "Hacker News 搜索超时。",
                    "稍后重试；不要循环重试。",
                ) from exc
            except httpx.HTTPError as exc:
                raise ProviderError(
                    "PROVIDER_UNAVAILABLE",
                    f"Hacker News 请求失败：{exc}",
                ) from exc

        if response.status_code == 429:
            raise ProviderError(
                "PROVIDER_RATE_LIMITED",
                "Hacker News 搜索接口限流。",
                "稍后重试。",
                retry_after_seconds=60,
            )
        if response.status_code >= 400:
            raise ProviderError(
                "PROVIDER_UNAVAILABLE",
                f"Hacker News 返回 HTTP {response.status_code}。",
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderError("PROVIDER_BAD_OUTPUT", "Hacker News 返回的不是 JSON。") from exc

        signals: list[Signal] = []
        for hit in payload.get("hits") or []:
            if not isinstance(hit, dict):
                continue
            title = strip_html(hit.get("title") or hit.get("story_title") or "", 300)
            object_id = str(hit.get("objectID") or "")
            url = str(hit.get("url") or "")
            if not url and object_id:
                url = f"https://news.ycombinator.com/item?id={object_id}"
            if not title or not url:
                continue
            quote = strip_html(hit.get("story_text") or "", 1200)
            points = hit.get("points")
            comments = hit.get("num_comments")
            if not quote:
                quote = f"{points or 0} points · {comments or 0} comments"
            signals.append(
                Signal(
                    id=make_signal_id(self.info.id, url, title),
                    provider_id=self.info.id,
                    source_type="post",
                    source_url=url,
                    title=title,
                    quote=quote,
                    author_public=hit.get("author"),
                    published_at=hit.get("created_at"),
                    metrics={
                        "points": points,
                        "comments": comments,
                        "object_id": object_id,
                    },
                )
            )
        return signals
