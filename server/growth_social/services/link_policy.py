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
from typing import Any
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
#: Bare tokens whose final host label is a common file extension are file
#: names, not links. Everything else fails closed as a possible link.
_IGNORED_FILE_SUFFIXES = frozenset(
    {
        "js",
        "jsx",
        "json",
        "ts",
        "tsx",
        "md",
        "py",
        "html",
        "css",
        "yml",
        "yaml",
        "sql",
        "sh",
        "rb",
        "go",
        "rs",
        "java",
        "txt",
    }
)
# Order matters: the scheme/protocol-relative and ``www.`` forms are matched
# first so the bare-domain branch never double-counts a URL inside them. A
# bare domain may have no path at all (``acme.io``) or only a query
# (``evil.com?x=1``); the file-extension denylist below removes obvious file
# names such as ``node.js`` without opening a path-only bypass.
_URL_PATTERN = re.compile(
    r"(?P<scheme>(?:https?:)?//[^\s<>\[\]\"'`)]+)"
    r"|(?P<www>www\.[^\s<>\[\]\"'`)]+)"
    r"|(?P<domain>(?<![\w@./-])"
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}"
    r"(?::\d+)?(?:[/?][^\s<>\[\]\"'`)]*)?)",
    re.IGNORECASE,
)
_TRAILING_PUNCTUATION = ".,;:!?'\""
_SCHEME_PATTERN = re.compile(r"https?://", re.IGNORECASE)


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


def _is_ignored_file_token(token: str) -> bool:
    """Whether a bare-domain token looks like ``name.ext``.

    Only filename-shaped tokens (no path or query) are ignored. Suffixes such
    as ``md``, ``py``, ``rs``, ``sh``, ``ts`` and ``go`` are also real ccTLDs,
    so ``evil.md/path`` must stay counted as a URL; otherwise a second link
    could slip past the exactly-one-link rule.
    """
    host_part = re.split(r"[/?#]", token, maxsplit=1)[0]
    if host_part != token:
        return False
    host_part = host_part.split(":", 1)[0]
    suffix = host_part.rsplit(".", 1)[-1].lower()
    return suffix in _IGNORED_FILE_SUFFIXES


def _extract_urls(text: str) -> list[tuple[str, int]]:
    """Return ``(cleaned_url, start_offset)`` for each URL token in ``text``.

    Detects explicit ``http(s)://`` links (any case), protocol-relative
    ``//host`` links, ``www.`` prefixed links, and bare domains with an
    optional path or query. Each token is counted once: markdown links and
    autolinks contribute only the URL inside them, and bare file names with a
    known source-code/data suffix are ignored.
    """
    found: list[tuple[str, int]] = []
    for match in _URL_PATTERN.finditer(text):
        cleaned = match.group(0).rstrip(_TRAILING_PUNCTUATION)
        if not cleaned:
            continue
        if match.lastgroup == "domain" and _is_ignored_file_token(cleaned):
            continue
        found.append((cleaned, match.start()))
    return found


def _parse_url(token: str) -> tuple[Any, bool]:
    """Parse a detected token; return ``(urlsplit_result, has_http_scheme)``.

    Scheme-less forms are parsed with a placeholder scheme so the host and path
    checks still run; the missing scheme is then reported as ``INVALID_URL``.
    """
    has_scheme = bool(_SCHEME_PATTERN.match(token))
    if has_scheme:
        candidate = token
    elif token.startswith("//"):
        candidate = "http:" + token
    else:
        candidate = "http://" + token
    try:
        return urlsplit(candidate), has_scheme
    except ValueError:
        return None, has_scheme


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

        parts, has_scheme = _parse_url(link_url)
        host = None
        if parts is not None:
            try:
                host = parts.hostname.lower() if parts.hostname else None
            except ValueError:
                host = None

        # Fail closed: a token without an http(s) scheme, an unparseable URL,
        # or one without a host is invalid even if its text looks plausible.
        if parts is None or not has_scheme or not host:
            violations.append("INVALID_URL")

        if host is not None and parts is not None:
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
