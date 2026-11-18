"""Hacker News source adapter.

Fetches recent stories from the public Algolia Hacker News search API and
normalizes each hit into a :class:`~growth_core.adapters.base.RawPost` row.
Algolia needs no credentials, so no secret is ever read or embedded in an
error.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from growth_core.adapters.base import (
    AdapterHealth,
    ProviderAuthError,
    ProviderBadOutput,
    ProviderNotConfigured,
    ProviderRateLimited,
    ProviderUnavailable,
    RawPost,
    SecretResolver,
)
from growth_core.adapters.registry import register_adapter
from growth_core.schemas import GrowthSource, ProviderConfig

__all__ = ["HackerNewsAdapter"]

_DEFAULT_BASE_URL = "https://hn.algolia.com"
_DEFAULT_LIMIT = 25
_MIN_LIMIT = 1
_MAX_LIMIT = 100
_AUTH_HTTP_STATUSES = (401, 403)
_ITEM_URL = "https://news.ycombinator.com/item?id={post_id}"


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _first_non_empty_str(*values: Any) -> str:
    """Return the first non-empty string, treating other types as absent."""
    for value in values:
        if isinstance(value, str) and value:
            return value
    return ""


def _parse_limit(raw: Any) -> int:
    """Validate and clamp the ``limit`` config value."""
    if raw is None:
        return _DEFAULT_LIMIT
    # ``bool`` is an ``int`` subclass but is not a meaningful limit.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: hackernews limit")
    return max(_MIN_LIMIT, min(_MAX_LIMIT, raw))


def _retry_after_seconds(response: httpx.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


class HackerNewsAdapter:
    """Fetch recent stories from Algolia's Hacker News search API."""

    name = "hackernews"
    capabilities: dict[str, Any] = {"social_source": True}

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._owns_client = False

    @classmethod
    def from_config(
        cls,
        config: ProviderConfig,
        secrets: SecretResolver,
    ) -> "HackerNewsAdapter":
        """Build an adapter from a provider config.

        Algolia requires no credentials, so ``secrets`` is unused. When this
        method creates the HTTP client, :meth:`aclose` closes it.
        """
        config_data = config.config if isinstance(config.config, dict) else {}
        base_url = config_data.get("base_url", _DEFAULT_BASE_URL)
        adapter = cls(
            client=httpx.AsyncClient(timeout=20),
            base_url=base_url,
        )
        adapter._owns_client = True
        return adapter

    def validate_config(self) -> None:
        """Adapter-level configuration is validated per source in ``fetch``."""
        return None

    async def health(self) -> AdapterHealth:
        """Report readiness without making a network call."""
        return AdapterHealth(name="hackernews", status="ready")

    async def aclose(self) -> None:
        """Close the HTTP client only when this adapter owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, source: GrowthSource) -> list[RawPost]:
        """Fetch and normalize recent stories for ``source``."""
        source_config = source.config if isinstance(source.config, dict) else {}
        query = source_config.get("query")
        if not _is_non_empty_str(query):
            raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: hackernews query")
        query = query.strip()
        limit = _parse_limit(source_config.get("limit"))

        try:
            response = await self._client.get(
                f"{self._base_url}/api/v1/search_by_date",
                params={
                    "query": query,
                    "tags": "story",
                    "hitsPerPage": limit,
                },
            )
        except httpx.TimeoutException as exc:
            # v1 maps timeouts to ProviderUnavailable per the task brief.
            raise ProviderUnavailable("hackernews request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("hackernews request failed") from exc

        self._raise_for_status(response)
        hits = self._hits(response)

        posts: list[RawPost] = []
        for hit in hits:
            post = self._parse_hit(hit)
            if post is not None:
                posts.append(post)
        return posts

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if status == 200:
            return
        if status == 404:
            raise ProviderNotConfigured(
                "PROVIDER_NOT_CONFIGURED: hackernews endpoint may not exist"
            )
        if status in _AUTH_HTTP_STATUSES:
            raise ProviderAuthError(
                f"hackernews rejected the credentials (HTTP {status})"
            )
        if status == 429:
            raise ProviderRateLimited(
                "PROVIDER_RATE_LIMITED: hackernews rate limited",
                retry_after_seconds=_retry_after_seconds(response),
            )
        if status >= 500:
            raise ProviderUnavailable(f"hackernews is unavailable (HTTP {status})")
        raise ProviderUnavailable(f"hackernews rejected the request (HTTP {status})")

    @staticmethod
    def _hits(response: httpx.Response) -> list[Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderBadOutput("hackernews response was not valid JSON") from exc
        hits = payload.get("hits") if isinstance(payload, dict) else None
        if not isinstance(hits, list):
            raise ProviderBadOutput("hackernews response was missing hits")
        return hits

    @staticmethod
    def _parse_hit(hit: Any) -> RawPost | None:
        if not isinstance(hit, dict):
            return None

        raw_post_id = hit.get("objectID")
        if raw_post_id is None:
            return None
        post_id = str(raw_post_id)
        if not post_id.strip():
            return None

        title = hit.get("title")
        title = title if isinstance(title, str) else ""
        body = _first_non_empty_str(
            hit.get("story_text"), hit.get("comment_text")
        )

        author = hit.get("author")
        url = hit.get("url")
        source_url = url if _is_non_empty_str(url) else _ITEM_URL.format(post_id=post_id)

        published_at = None
        created_at_i = hit.get("created_at_i")
        if created_at_i is not None:
            try:
                published_at = datetime.fromtimestamp(
                    created_at_i, tz=timezone.utc
                )
            except (OverflowError, TypeError, ValueError, OSError):
                published_at = None

        return RawPost(
            platform="hackernews",
            platform_post_id=post_id,
            title=title,
            body=body,
            author_public=author if isinstance(author, str) else None,
            source_url=source_url,
            published_at=published_at,
            metrics={
                "points": hit.get("points", 0),
                "comments": hit.get("num_comments", 0),
            },
            subreddit=None,
            raw=hit,
        )


@register_adapter("social_source", "hackernews")
def _hackernews_factory(
    config: ProviderConfig, secrets: SecretResolver
) -> HackerNewsAdapter:
    return HackerNewsAdapter.from_config(config, secrets)
