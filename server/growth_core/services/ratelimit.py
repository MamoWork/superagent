"""Send-time rate-limit policy for the social pipeline.

Rules live in ``rate_limit_rules`` per tenant and channel. Policy is resolved
here, and counters are consumed atomically by the repository so a denied send
never leaves partial increments behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from growth_core.repositories.base import GrowthRepository
from growth_core.schemas import (
    RateLimitCheck,
    RateLimitDecision,
    RateLimitRule,
)

__all__ = ["RateLimitContext", "check_send_allowed"]


@dataclass(frozen=True)
class RateLimitContext:
    """Everything needed to decide whether a social send may proceed."""

    tenant_id: UUID
    channel: str
    platform: str
    subreddit: str | None
    has_link: bool
    now: datetime


def _pick(
    rules: list[RateLimitRule], scope: str, scope_key: str
) -> RateLimitRule | None:
    """First enabled rule for the exact key, else the ``"*"`` fallback."""
    exact = next(
        (
            rule
            for rule in rules
            if rule.scope == scope and rule.scope_key == scope_key
        ),
        None,
    )
    if exact is not None:
        return exact
    return next(
        (
            rule
            for rule in rules
            if rule.scope == scope and rule.scope_key == "*"
        ),
        None,
    )


async def check_send_allowed(
    repo: GrowthRepository, ctx: RateLimitContext
) -> RateLimitDecision:
    """Resolve and consume the rate-limit checks for one social send.

    Fails closed: a tenant without an enabled global rule can never send.
    """
    rules = [
        rule
        for rule in await repo.list_rate_limit_rules(
            ctx.tenant_id, channel=ctx.channel
        )
        if rule.enabled
    ]

    global_rule = next(
        (rule for rule in rules if rule.scope == "global"), None
    )
    if global_rule is None:
        return RateLimitDecision(
            allowed=False,
            exceeded_scope="global",
            exceeded_scope_key="*",
            retry_after_seconds=0,
        )

    checks = [
        RateLimitCheck(
            channel=ctx.channel,
            scope="global",
            scope_key="*",
            max_count=global_rule.max_count,
            window_seconds=global_rule.window_seconds,
        )
    ]

    platform_rule = _pick(rules, "platform", ctx.platform)
    if platform_rule is not None:
        checks.append(
            RateLimitCheck(
                channel=ctx.channel,
                scope="platform",
                scope_key=ctx.platform,
                max_count=platform_rule.max_count,
                window_seconds=platform_rule.window_seconds,
            )
        )

    if ctx.platform == "reddit" and ctx.subreddit and ctx.has_link:
        subreddit_rule = _pick(rules, "subreddit", ctx.subreddit)
        if subreddit_rule is not None:
            checks.append(
                RateLimitCheck(
                    channel=ctx.channel,
                    scope="subreddit",
                    scope_key=ctx.subreddit,
                    max_count=subreddit_rule.max_count,
                    window_seconds=subreddit_rule.window_seconds,
                )
            )

    return await repo.consume_rate_limits(ctx.tenant_id, checks, now=ctx.now)
