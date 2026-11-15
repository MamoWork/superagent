"""Transactional outbox dispatcher for the Growth Agent.

The dispatcher drains claimed outbox rows and delivers them to their external
destination. Delivery failures are recorded on the row through
``mark_outbox_failed`` so the repository applies its retry/backoff and
dead-letter policy; nothing here logs payload contents or secrets.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from growth_core.adapters.base import Notifier
from growth_core.repositories.base import GrowthRepository

__all__ = ["dispatch_outbox"]

_FEISHU_CARD_TOPIC = "feishu.card"
_PAYLOAD_KEYS = ("chat_id", "card", "approval_id")


async def dispatch_outbox(
    repo: GrowthRepository,
    notifier: Notifier,
    *,
    limit: int = 10,
    now: datetime | None = None,
) -> int:
    """Claim and deliver up to ``limit`` outbox messages.

    Returns the number of messages successfully delivered and marked sent.
    Unknown topics are marked failed with ``unsupported topic``; per-message
    delivery errors are recorded as ``"{ExceptionType}: {message}"``.
    """
    messages = await repo.claim_outbox(limit=limit, now=now)
    sent = 0

    for message in messages:
        if message.topic != _FEISHU_CARD_TOPIC:
            await repo.mark_outbox_failed(
                message.id, "unsupported topic", now=now
            )
            continue

        try:
            payload: dict[str, Any] = message.payload
            chat_id, card, approval_id = (
                payload.get(key) for key in _PAYLOAD_KEYS
            )
            if chat_id is None:
                raise ValueError(
                    "malformed feishu.card payload: missing chat_id"
                )
            if card is None:
                raise ValueError(
                    "malformed feishu.card payload: missing card"
                )
            if approval_id is None:
                raise ValueError(
                    "malformed feishu.card payload: missing approval_id"
                )
            external_id = await notifier.send_card(chat_id, card)
            await repo.set_approval_external_id(
                message.tenant_id, approval_id, external_id
            )
            await repo.mark_outbox_sent(message.id)
        except Exception as exc:  # noqa: BLE001 - recorded, then next message
            await repo.mark_outbox_failed(
                message.id, f"{type(exc).__name__}: {exc}", now=now
            )
            continue

        sent += 1

    return sent
