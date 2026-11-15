from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[1]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class Settings:
    """Local runtime settings. No secrets are stored here."""

    db_path: Path = field(
        default_factory=lambda: Path(
            os.environ.get(
                "OPPORTUNITY_SCOUT_DB",
                str(SERVER_ROOT / "data" / "opportunity_scout.db"),
            )
        )
    )
    # Optional override for the built Vite directory (tests / custom deploys).
    web_dist_dir: Path | None = field(
        default_factory=lambda: (
            Path(os.environ["OPPORTUNITY_WEB_DIST"]).expanduser()
            if os.environ.get("OPPORTUNITY_WEB_DIST")
            else None
        )
    )
    agent_reach_bin: str = field(
        default_factory=lambda: os.environ.get("AGENT_REACH_BIN", "agent-reach")
    )
    agent_reach_timeout: float = field(
        default_factory=lambda: _env_float("AGENT_REACH_TIMEOUT", 90.0)
    )
    agent_reach_channels: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip()
            for item in os.environ.get("AGENT_REACH_CHANNELS", "reddit,web").split(",")
            if item.strip()
        )
    )
    api_host: str = field(default_factory=lambda: os.environ.get("API_HOST", "127.0.0.1"))
    api_port: int = field(
        default_factory=lambda: int(os.environ.get("API_PORT", "8765"))
    )
    http_timeout: float = field(
        default_factory=lambda: _env_float("OPPORTUNITY_HTTP_TIMEOUT", 25.0)
    )

    # Optional RSS / Atom feeds, comma separated. Empty means the provider is
    # registered but reported as not configured.
    rss_feeds: tuple[str, ...] = field(
        default_factory=lambda: tuple(
            item.strip()
            for item in os.environ.get("OPPORTUNITY_RSS_FEEDS", "").split(",")
            if item.strip()
        )
    )
    trends_geo: str = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_TRENDS_GEO", "US")
    )

    # Amazon Creators API credentials are BYO-key. Secrets stay in the
    # environment and are never persisted or returned by the API.
    amazon_credential_id: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AMAZON_CREDENTIAL_ID") or None,
        repr=False,
    )
    amazon_credential_secret: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AMAZON_CREDENTIAL_SECRET") or None,
        repr=False,
    )
    amazon_tag: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AMAZON_TAG") or None,
        repr=False,
    )
    amazon_version: str = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AMAZON_VERSION", "3.1")
    )
    amazon_country: str = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AMAZON_COUNTRY", "US")
    )

    # AI analysis is BYO-key and disabled by default. Keys are read from the
    # environment at runtime and never persisted by this application.
    ai_provider: str = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AI_PROVIDER", "auto")
    )
    ai_model: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AI_MODEL") or None
    )
    ai_base_url: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AI_BASE_URL") or None
    )
    ai_api_key: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_AI_API_KEY") or None,
        repr=False,
    )
    ai_timeout: float = field(
        default_factory=lambda: _env_float("OPPORTUNITY_AI_TIMEOUT", 120.0)
    )
    ai_max_signals: int = field(
        default_factory=lambda: _env_int("OPPORTUNITY_AI_MAX_SIGNALS", 40)
    )
    ai_max_chars_per_signal: int = field(
        default_factory=lambda: _env_int("OPPORTUNITY_AI_MAX_CHARS_PER_SIGNAL", 1200)
    )
    ai_max_total_chars: int = field(
        default_factory=lambda: _env_int("OPPORTUNITY_AI_MAX_TOTAL_CHARS", 30000)
    )

    scheduler_enabled: bool = field(
        default_factory=lambda: _env_bool("OPPORTUNITY_SCHEDULER_ENABLED", True)
    )
    scheduler_timezone: str | None = field(
        default_factory=lambda: os.environ.get("OPPORTUNITY_SCHEDULER_TIMEZONE") or None
    )
