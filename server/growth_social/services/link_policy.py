"""Link policy for social replies and UTM link construction.

Every published reply carries exactly one official deep link. The link must
point at the product domain, include UTM parameters, follow a disclosure that
appears before the link, and not sit in the first sentence. The model never
gets to decide these rules: the server validates the final text.

:func:`validate_link_policy` collects every violation it can detect instead of
returning after the first one, so an operator sees the whole failure at once.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

__all__ = [
    "LinkPolicyConfig",
    "LinkPolicyResult",
    "SHORTENER_HOSTS",
    "UTM_SOURCES",
    "build_utm_url",
    "validate_link_policy",
]

SHORTENER_HOSTS = frozenset(
    {
        "bit.ly",
        "t.co",
        "goo.gl",
        "tinyurl.com",
        "ow.ly",
        "buff.ly",
        "rebrand.ly",
        "cutt.ly",
        "is.gd",
        "rb.gy",
    }
)

UTM_SOURCES = {"reddit": "reddit", "hackernews": "hn"}

_DISCLOSURE_PHRASES = (
    "i built",
    "i work on",
    "our team built",
    "we built",
    "i'm building",
    "i am building",
)

_UTM_KEYS = frozenset({"utm_source", "utm_medium", "utm_campaign"})
_URL_PATTERN = re.compile(r"https?://[^\s)\]>]+")
_TRAILING_PUNCTUATION = ".,;:!?'\""


@dataclass(frozen=True)
class LinkPolicyConfig:
    """Rules applied to a rendered reply."""

    allowed_domain: str
    utm_medium: str = "reply"
    require_disclosure: bool = True


@dataclass(frozen=True)
class LinkPolicyResult:
    """Outcome of validating one reply body."""

    ok: bool
    link_url: str | None
    violations: list[str] = field(default_factory=list)
    manual_only: bool = False


def _extract_urls(text: str) -> list[tuple[str, int]]:
    """Return ``(cleaned_url, start_offset)`` for each URL found in ``text``."""
    found: list[tuple[str, int]] = []
    for match in _URL_PATTERN.finditer(text):
        cleaned = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if cleaned.endswith(")"):
            cleaned = cleaned[:-1]
        found.append((cleaned, match.start()))
    return found


def _first_sentence_end(text: str) -> int:
    """Index of the first ``". "`` or newline, or ``len(text)`` if none."""
    end = len(text)
    for marker in (". ", "\n"):
        index = text.find(marker)
        if index != -1 and index < end:
            end = index
    return end


def _host_matches(host: str, domain: str) -> bool:
    if not domain:
        return False
    return host == domain or host.endswith("." + domain)


def _is_shortener(host: str) -> bool:
    return any(_host_matches(host, shortener) for shortener in SHORTENER_HOSTS)


def build_utm_url(
    base_url: str,
    link_path: str,
    *,
    lead_id: str,
    platform: str,
) -> str:
    """Join ``link_path`` onto ``base_url`` and add the required UTM values.

    ``link_path`` must be a path, never an absolute or protocol-relative URL,
    and may not contain ``..`` segments. Existing query parameters are kept;
    UTM keys are replaced with the server-chosen values.
    """
    if (
        link_path.startswith("http://")
        or link_path.startswith("https://")
        or link_path.startswith("//")
        or ".." in link_path
    ):
        raise ValueError(f"INVALID_LINK_PATH: {link_path}")

    path = link_path if link_path.startswith("/") else "/" + link_path
    parts = urlsplit(base_url.rstrip("/") + path)

    params = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _UTM_KEYS
    ]
    params.extend(
        (
            ("utm_source", UTM_SOURCES.get(platform, platform)),
            ("utm_medium", "reply"),
            ("utm_campaign", str(lead_id)),
        )
    )

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(params),
            parts.fragment,
        )
    )


def validate_link_policy(
    text: str,
    config: LinkPolicyConfig,
    *,
    subreddit_allows_links: bool = True,
) -> LinkPolicyResult:
    """Validate every link rule and return all violations found."""
    violations: list[str] = []
    urls = _extract_urls(text)
    link_url: str | None = None

    if not urls:
        violations.append("NO_LINK")
    elif len(urls) > 1:
        violations.append("MULTIPLE_LINKS")
    else:
        link_url, url_start = urls[0]

        parts = None
        try:
            parts = urlsplit(link_url)
        except ValueError:
            parts = None

        host = parts.hostname.lower() if parts and parts.hostname else None
        if parts is None or parts.scheme not in ("http", "https") or not host:
            violations.append("INVALID_URL")
        else:
            if _is_shortener(host):
                violations.append("SHORTENER")

            allowed = config.allowed_domain.lower().strip().lstrip(".")
            if not _host_matches(host, allowed):
                violations.append("WRONG_DOMAIN")

            if not parts.path or parts.path == "/":
                violations.append("NOT_DEEP_LINK")

            query = dict(parse_qsl(parts.query, keep_blank_values=True))
            if (
                not query.get("utm_source")
                or query.get("utm_medium") != config.utm_medium
                or not query.get("utm_campaign")
            ):
                violations.append("MISSING_UTM")

        if config.require_disclosure:
            prefix = text[:url_start].lower()
            if not any(phrase in prefix for phrase in _DISCLOSURE_PHRASES):
                violations.append("MISSING_DISCLOSURE")

        if url_start < _first_sentence_end(text):
            violations.append("LINK_TOO_EARLY")

    manual_only = False
    if not subreddit_allows_links:
        manual_only = True
        violations.append("SUBREDDIT_NO_LINKS")

    return LinkPolicyResult(
        ok=not violations,
        link_url=link_url,
        violations=violations,
        manual_only=manual_only,
    )
