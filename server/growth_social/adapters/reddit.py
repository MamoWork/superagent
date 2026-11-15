"""Reddit source adapter.

Fetches the newest posts from a subreddit through Reddit's public JSON
endpoint and normalizes them into :class:`~growth_core.adapters.base.RawPost`
rows. Error messages are secret-free: the configured user agent is never
embedded in a raised error.
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

__all__ = ["RedditAdapter"]

_DEFAULT_BASE_URL = "https://www.reddit.com"
_DEFAULT_LIMIT = 25
_MIN_LIMIT = 1
_MAX_LIMIT = 100
_AUTH_HTTP_STATUSES = (401, 403)


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _parse_limit(raw: Any) -> int:
    """Validate and clamp the ``limit`` config value."""
    if raw is None:
        return _DEFAULT_LIMIT
    # ``bool`` is an ``int`` subclass but is not a meaningful limit.
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: reddit limit")
    return max(_MIN_LIMIT, min(_MAX_LIMIT, raw))


def _parse_keywords(raw: Any) -> list[str]:
    """Validate the optional ``keywords`` config value."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: reddit keywords")
    return [item for item in raw if _is_non_empty_str(item)]


def _retry_after_seconds(response: httpx.Response) -> int | None:
    value = response.headers.get("retry-after")
    if value is None:
        return None
    try:
        return int(value.strip())
    except (TypeError, ValueError):
        return None


class RedditAdapter:
    """Fetch posts from a subreddit's ``new.json`` feed."""

    name = "reddit"
    capabilities: dict[str, Any] = {"social_source": True}

    def __init__(
        self,
        *,
        client: httpx.AsyncClient,
        user_agent: str,
        base_url: str = _DEFAULT_BASE_URL,
    ) -> None:
        if not _is_non_empty_str(user_agent):
            raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: reddit user_agent")
        self._client = client
        self._user_agent = user_agent
        self._base_url = base_url.rstrip("/")
        self._owns_client = False

    @classmethod
    def from_config(
        cls,
        config: ProviderConfig,
        secrets: SecretResolver,
    ) -> "RedditAdapter":
        """Build an adapter from a provider config and a secret resolver.

        The user agent is resolved through ``secrets`` when ``secret_ref`` is
        set, otherwise from ``config.config["user_agent"]``. When this method
        creates the HTTP client, :meth:`aclose` closes it.
        """
        config_data = config.config if isinstance(config.config, dict) else {}
        if config.secret_ref:
            user_agent = secrets.get(config.secret_ref)
        else:
            user_agent = config_data.get("user_agent")

        if not _is_non_empty_str(user_agent):
            raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: reddit user_agent")

        base_url = config_data.get("base_url", _DEFAULT_BASE_URL)
        adapter = cls(
            client=httpx.AsyncClient(timeout=20),
            user_agent=user_agent,
            base_url=base_url,
        )
        adapter._owns_client = True
        return adapter

    def validate_config(self) -> None:
        """Adapter-level configuration is validated per source in ``fetch``."""
        return None

    async def health(self) -> AdapterHealth:
        """Report readiness without making a network call."""
        return AdapterHealth(name="reddit", status="ready")

    async def aclose(self) -> None:
        """Close the HTTP client only when this adapter owns it."""
        if self._owns_client:
            await self._client.aclose()

    async def fetch(self, source: GrowthSource) -> list[RawPost]:
        """Fetch and normalize the newest posts for ``source``."""
        source_config = source.config if isinstance(source.config, dict) else {}
        subreddit = source_config.get("subreddit")
        if not _is_non_empty_str(subreddit):
            raise ProviderNotConfigured("PROVIDER_NOT_CONFIGURED: reddit subreddit")
        subreddit = subreddit.strip()
        limit = _parse_limit(source_config.get("limit"))
        keywords = _parse_keywords(source_config.get("keywords"))

        try:
            response = await self._client.get(
                f"{self._base_url}/r/{subreddit}/new.json",
                params={"limit": limit},
                headers={"User-Agent": self._user_agent},
            )
        except httpx.TimeoutException as exc:
            # v1 maps timeouts to ProviderUnavailable per the task brief.
            raise ProviderUnavailable("reddit request timed out") from exc
        except httpx.HTTPError as exc:
            raise ProviderUnavailable("reddit request failed") from exc

        self._raise_for_status(response, subreddit)
        children = self._children(response)

        posts: list[RawPost] = []
        for child in children:
            post = self._parse_child(child, keywords)
            if post is not None:
                posts.append(post)
        return posts

    # -- helpers ----------------------------------------------------------

    @staticmethod
    def _raise_for_status(response: httpx.Response, subreddit: str) -> None:
        status = response.status_code
        if status == 200:
            return
        if status == 404:
            raise ProviderNotConfigured(
                f"PROVIDER_NOT_CONFIGURED: reddit subreddit r/{subreddit} may not exist"
            )
        if status in _AUTH_HTTP_STATUSES:
            raise ProviderAuthError(f"reddit rejected the credentials (HTTP {status})")
        if status == 429:
            raise ProviderRateLimited(
                "PROVIDER_RATE_LIMITED: reddit rate limited",
                retry_after_seconds=_retry_after_seconds(response),
            )
        if status >= 500:
            raise ProviderUnavailable(f"reddit is unavailable (HTTP {status})")
        raise ProviderUnavailable(f"reddit rejected the request (HTTP {status})")

    @staticmethod
    def _children(response: httpx.Response) -> list[Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise ProviderBadOutput("reddit response was not valid JSON") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        children = data.get("children") if isinstance(data, dict) else None
        if not isinstance(children, list):
            raise ProviderBadOutput("reddit response was missing data.children")
        return children

    @staticmethod
    def _parse_child(child: Any, keywords: list[str]) -> RawPost | None:
        if not isinstance(child, dict):
            return None
        data = child.get("data")
        if not isinstance(data, dict):
            return None
        if data.get("stickied"):
            return None

        post_id = data.get("id")
        permalink = data.get("permalink")
        if not _is_non_empty_str(post_id) or not _is_non_empty_str(permalink):
            return None

        title = data.get("title")
        title = title if isinstance(title, str) else ""
        selftext = data.get("selftext")
        body = selftext if isinstance(selftext, str) else ""

        if keywords:
            haystack = f"{title}\n{body}".lower()
            if not any(keyword.lower() in haystack for keyword in keywords):
                return None

        author = data.get("author")
        subreddit = data.get("subreddit")
        published_at = None
        created_utc = data.get("created_utc")
        if created_utc is not None:
            try:
                published_at = datetime.fromtimestamp(created_utc, tz=timezone.utc)
            except (OverflowError, TypeError, ValueError, OSError):
                published_at = None

        return RawPost(
            platform="reddit",
            platform_post_id=post_id,
            title=title,
            body=body,
            author_public=author if isinstance(author, str) else None,
            source_url=f"https://www.reddit.com{permalink}",
            published_at=published_at,
            metrics={
                "score": data.get("score", 0),
                "comments": data.get("num_comments", 0),
            },
            subreddit=subreddit if isinstance(subreddit, str) else None,
            raw=data,
        )


@register_adapter("social_source", "reddit")
def _reddit_factory(config: ProviderConfig, secrets: SecretResolver) -> RedditAdapter:
    return RedditAdapter.from_config(config, secrets)
