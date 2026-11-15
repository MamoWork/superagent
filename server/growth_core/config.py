from __future__ import annotations

import os
from dataclasses import dataclass, field

_REQUIRED_ENV: tuple[tuple[str, str], ...] = (
    ("database_url", "GROWTH_DATABASE_URL"),
    ("service_token", "GROWTH_SERVICE_TOKEN"),
    ("tenant_id", "GROWTH_TENANT_ID"),
    ("workspace_id", "GROWTH_WORKSPACE_ID"),
)


class GrowthConfigError(Exception):
    """Raised when required Growth Agent configuration is missing."""


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


@dataclass(frozen=True)
class GrowthSettings:
    database_url: str = field(repr=False)
    service_token: str = field(repr=False)
    tenant_id: str
    workspace_id: str
    feishu_app_id: str = ""
    feishu_app_secret: str = field(default="", repr=False)
    feishu_verification_token: str = field(default="", repr=False)
    feishu_encrypt_key: str = field(default="", repr=False)
    feishu_chat_id: str = ""
    feishu_base_url: str = "https://open.feishu.cn"
    reddit_user_agent: str = "growth-agent/0.1"
    reddit_base_url: str = "https://www.reddit.com"
    hn_base_url: str = "https://hn.algolia.com"
    llm_model: str = ""
    llm_scoring_model: str = ""
    llm_drafting_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = field(default="", repr=False)
    llm_timeout_seconds: float = 60.0
    product_name: str = ""
    product_url: str = ""
    product_domain: str = ""
    global_daily_limit: int = 50
    reddit_daily_limit: int = 5
    subreddit_link_daily_limit: int = 2
    followup_max_total: int = 3
    followup_min_interval_hours: int = 24
    worker_id: str = "growth-worker-1"
    worker_poll_seconds: float = 2.0
    stale_lock_seconds: int = 600

    @classmethod
    def from_env(cls) -> "GrowthSettings":
        for _field_name, env_name in _REQUIRED_ENV:
            if not os.environ.get(env_name):
                raise GrowthConfigError(
                    f"Missing required environment variable: {env_name}"
                )
        return cls(
            database_url=os.environ["GROWTH_DATABASE_URL"],
            service_token=os.environ["GROWTH_SERVICE_TOKEN"],
            tenant_id=os.environ["GROWTH_TENANT_ID"],
            workspace_id=os.environ["GROWTH_WORKSPACE_ID"],
            feishu_app_id=os.environ.get("GROWTH_FEISHU_APP_ID", ""),
            feishu_app_secret=os.environ.get("GROWTH_FEISHU_APP_SECRET", ""),
            feishu_verification_token=os.environ.get(
                "GROWTH_FEISHU_VERIFICATION_TOKEN", ""
            ),
            feishu_encrypt_key=os.environ.get("GROWTH_FEISHU_ENCRYPT_KEY", ""),
            feishu_chat_id=os.environ.get("GROWTH_FEISHU_CHAT_ID", ""),
            feishu_base_url=os.environ.get(
                "GROWTH_FEISHU_BASE_URL", "https://open.feishu.cn"
            ),
            reddit_user_agent=os.environ.get(
                "GROWTH_REDDIT_USER_AGENT", "growth-agent/0.1"
            ),
            reddit_base_url=os.environ.get(
                "GROWTH_REDDIT_BASE_URL", "https://www.reddit.com"
            ),
            hn_base_url=os.environ.get("GROWTH_HN_BASE_URL", "https://hn.algolia.com"),
            llm_model=os.environ.get("GROWTH_LLM_MODEL", ""),
            llm_scoring_model=os.environ.get("GROWTH_LLM_SCORING_MODEL", ""),
            llm_drafting_model=os.environ.get("GROWTH_LLM_DRAFTING_MODEL", ""),
            llm_base_url=os.environ.get("GROWTH_LLM_BASE_URL", ""),
            llm_api_key=os.environ.get("GROWTH_LLM_API_KEY", ""),
            llm_timeout_seconds=_env_float("GROWTH_LLM_TIMEOUT_SECONDS", 60.0),
            product_name=os.environ.get("GROWTH_PRODUCT_NAME", ""),
            product_url=os.environ.get("GROWTH_PRODUCT_URL", ""),
            product_domain=os.environ.get("GROWTH_PRODUCT_DOMAIN", ""),
            global_daily_limit=_env_int("GROWTH_GLOBAL_DAILY_LIMIT", 50),
            reddit_daily_limit=_env_int("GROWTH_REDDIT_DAILY_LIMIT", 5),
            subreddit_link_daily_limit=_env_int(
                "GROWTH_SUBREDDIT_LINK_DAILY_LIMIT", 2
            ),
            followup_max_total=_env_int("GROWTH_FOLLOWUP_MAX_TOTAL", 3),
            followup_min_interval_hours=_env_int(
                "GROWTH_FOLLOWUP_MIN_INTERVAL_HOURS", 24
            ),
            worker_id=os.environ.get("GROWTH_WORKER_ID", "growth-worker-1"),
            worker_poll_seconds=_env_float("GROWTH_WORKER_POLL_SECONDS", 2.0),
            stale_lock_seconds=_env_int("GROWTH_STALE_LOCK_SECONDS", 600),
        )
