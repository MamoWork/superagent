"""HTTP routes for the social Growth Agent module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from growth_core.api.deps import RequestContext, get_context, require_service_token
from growth_core.schemas import (
    NewAuditEntry,
    NewOutreachVersion,
    NewTask,
)
from growth_core.services.feishu_signature import (
    verify_feishu_signature,
    verify_feishu_token,
)
from growth_social.services.approval import (
    ensure_approval_and_enqueue_card,
    handle_approval,
    parse_feishu_action,
    subreddit_allows_links,
)
from growth_social.services.link_policy import (
    LinkPolicyConfig,
    validate_link_policy,
)
from growth_social.services.sending import SendBlocked, mark_sent

protected_router = APIRouter(dependencies=[Depends(require_service_token)])
callback_router = APIRouter()


class LeadTaskRequest(BaseModel):
    lead_id: UUID


class ReviseRequest(BaseModel):
    body_markdown: str
    operator: str = Field(min_length=1)


class MarkSentRequest(BaseModel):
    sent_at: datetime | None = None
    channel: str = "manual"


def _clamp_limit(limit: int) -> int:
    return max(1, min(200, limit))


async def _enqueue(
    request: Request,
    ctx: RequestContext,
    task_type: str,
    payload: dict[str, object],
    idempotency_key: str,
) -> dict[str, str]:
    task_id = await request.app.state.repo.enqueue_task(
        NewTask(
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            pipeline="social",
            task_type=task_type,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    )
    return {"task_id": str(task_id)}


@protected_router.post("/internal/v1/social/ingest")
async def ingest(
    request: Request, ctx: RequestContext = Depends(get_context)
) -> dict[str, str]:
    if not ctx.idempotency_key:
        raise HTTPException(
            status_code=400, detail={"code": "INVALID_IDEMPOTENCY_KEY"}
        )
    return await _enqueue(
        request, ctx, "social.ingest", {}, ctx.idempotency_key
    )


@protected_router.post("/internal/v1/social/score")
async def score(
    body: LeadTaskRequest,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> dict[str, str]:
    return await _enqueue(
        request,
        ctx,
        "social.score",
        {"lead_id": str(body.lead_id)},
        f"score:{body.lead_id}",
    )


@protected_router.post("/internal/v1/social/draft")
async def draft(
    body: LeadTaskRequest,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> dict[str, str]:
    return await _enqueue(
        request,
        ctx,
        "social.draft",
        {"lead_id": str(body.lead_id)},
        f"draft:{body.lead_id}",
    )


@protected_router.get("/api/growth/social/leads")
async def list_leads(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50),
    ctx: RequestContext = Depends(get_context),
) -> list[dict[str, object]]:
    rows = await request.app.state.repo.list_leads(
        ctx.tenant_id,
        status=status or None,
        limit=_clamp_limit(limit),
    )
    return [row.model_dump(mode="json") for row in rows]


@protected_router.get("/api/growth/social/messages")
async def list_messages(
    request: Request,
    status: str | None = Query(default=None),
    limit: int = Query(default=50),
    ctx: RequestContext = Depends(get_context),
) -> list[dict[str, object]]:
    rows = await request.app.state.repo.list_messages(
        ctx.tenant_id,
        status=status or None,
        limit=_clamp_limit(limit),
    )
    return [row.model_dump(mode="json") for row in rows]


# ---------------------------------------------------------------------------
# Feishu approval callback
# ---------------------------------------------------------------------------

#: Feishu cannot send the service token, so the callback lives on its own
#: router (no router-level dependency) and is authenticated only by the
#: signature or verification-token check below.
_CALLBACK_PATH = "/internal/v1/approvals/callback"

_TOAST_BY_STATUS = {
    "approved": ("success", "Reply approved."),
    "rejected": ("success", "Reply rejected."),
    "already_decided": ("error", "This approval was already decided."),
    "not_found": ("error", "Approval not found."),
}


def _parse_json_body(body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400, detail={"code": "INVALID_JSON"}
        ) from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail={"code": "INVALID_JSON"})
    return payload


@callback_router.post(_CALLBACK_PATH)
async def feishu_approval_callback(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    repo = request.app.state.repo
    body = await request.body()

    if settings.feishu_encrypt_key:
        if not verify_feishu_signature(
            request.headers, body, settings.feishu_encrypt_key
        ):
            raise HTTPException(status_code=403, detail="invalid feishu signature")
        payload = _parse_json_body(body)
    else:
        payload = _parse_json_body(body)
        if not verify_feishu_token(payload, settings.feishu_verification_token):
            raise HTTPException(status_code=403, detail="invalid feishu token")

    # Feishu URL verification: echo the challenge after token/signature checks.
    if payload.get("type") == "url_verification":
        challenge = payload.get("challenge")
        if not isinstance(challenge, str):
            raise HTTPException(status_code=400, detail="missing challenge")
        return {"challenge": challenge}

    try:
        action = parse_feishu_action(payload)
    except ValueError:
        return {
            "toast": {
                "type": "error",
                "content": "Invalid approval action.",
            }
        }

    result = await handle_approval(
        repo,
        tenant_id=UUID(settings.tenant_id),
        action=action,
        now=datetime.now(timezone.utc),
    )
    toast_type, content = _TOAST_BY_STATUS.get(
        result.status, ("success", result.reason or "Recorded.")
    )
    if result.status == "pending" and result.reason:
        content = result.reason
    return {"toast": {"type": toast_type, "content": content}}


# ---------------------------------------------------------------------------
# Operator revision
# ---------------------------------------------------------------------------


@protected_router.post("/api/growth/social/messages/{message_id}/revise")
async def revise_message(
    message_id: UUID,
    body: ReviseRequest,
    request: Request,
    ctx: RequestContext = Depends(get_context),
) -> dict[str, object]:
    repo = request.app.state.repo
    settings = request.app.state.settings

    message = await repo.get_message(ctx.tenant_id, message_id)
    if message is None:
        raise HTTPException(
            status_code=404, detail={"code": "MESSAGE_NOT_FOUND"}
        )
    if message.status not in ("draft_ready", "approved"):
        raise HTTPException(
            status_code=409, detail={"code": "MESSAGE_NOT_REVISABLE"}
        )

    lead = None
    if message.lead_id is not None:
        lead = await repo.get_lead(ctx.tenant_id, message.lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail={"code": "LEAD_NOT_FOUND"})

    policy = validate_link_policy(
        body.body_markdown,
        LinkPolicyConfig(allowed_domain=settings.product_domain),
        subreddit_allows_links=subreddit_allows_links(lead),
    )
    if policy.manual_only or not policy.ok or not policy.link_url:
        raise HTTPException(
            status_code=422, detail={"violations": policy.violations}
        )

    latest = await repo.get_latest_version(ctx.tenant_id, message_id)
    if latest is None:
        raise HTTPException(
            status_code=409, detail={"code": "MESSAGE_NOT_REVISABLE"}
        )
    new_version_number = latest.version + 1

    # Create the immutable version first (brief order). A concurrent revision
    # loses the unique ``(message_id, version)`` insert and must surface 409.
    try:
        version = await repo.create_version(
            NewOutreachVersion(
                tenant_id=ctx.tenant_id,
                message_id=message_id,
                version=new_version_number,
                body_text=body.body_markdown,
                cta_url=policy.link_url,
            )
        )
    except Exception as exc:  # noqa: BLE001 - typed check by class name below
        if type(exc).__name__ == "UniqueViolationError":
            raise HTTPException(
                status_code=409, detail={"code": "REVISION_CONFLICT"}
            ) from None
        raise

    # Old cards must never be able to approve the new version.
    await repo.expire_pending_approvals(ctx.tenant_id, message_id)

    moved = await repo.update_message_status(
        ctx.tenant_id,
        message_id,
        expected_status=message.status,
        status="draft_ready",
        metadata_patch={"draft_version": new_version_number},
    )
    if not moved:
        # The orphan version row is accepted; audit the lost transition.
        await repo.write_audit(
            NewAuditEntry(
                tenant_id=ctx.tenant_id,
                workspace_id=message.workspace_id,
                actor_type="user",
                actor_id=body.operator,
                action="social.approval_conflict",
                entity_type="outreach_message",
                entity_id=message_id,
                after={
                    "approval_id": f"{message.id}:v{new_version_number}",
                    "expected_status": message.status,
                    "attempted_status": "draft_ready",
                },
            )
        )
        raise HTTPException(
            status_code=409, detail={"code": "REVISION_CONFLICT"}
        )

    approval_id = f"{message.id}:v{new_version_number}"
    approval = await ensure_approval_and_enqueue_card(
        repo,
        tenant_id=ctx.tenant_id,
        workspace_id=message.workspace_id,
        message=message,
        approval_id=approval_id,
        lead=lead,
        version=version,
        settings=settings,
        clock=datetime.now(timezone.utc),
    )
    await repo.write_audit(
        NewAuditEntry(
            tenant_id=ctx.tenant_id,
            workspace_id=message.workspace_id,
            actor_type="user",
            actor_id=body.operator,
            action="social.revised",
            entity_type="outreach_message",
            entity_id=message_id,
            after={"version": new_version_number},
        )
    )
    return {
        "message_id": str(message_id),
        "status": "draft_ready",
        "version": new_version_number,
        "approval_id": approval.approval_id,
    }


# ---------------------------------------------------------------------------
# Manual send tracking
# ---------------------------------------------------------------------------


@protected_router.post("/api/growth/social/messages/{message_id}/sent")
async def mark_message_sent(
    message_id: UUID,
    request: Request,
    body: MarkSentRequest | None = None,
    ctx: RequestContext = Depends(get_context),
) -> dict[str, object]:
    channel = body.channel if body is not None and body.channel else "manual"
    sent_at = body.sent_at if body is not None else None
    try:
        message = await mark_sent(
            request.app.state.repo,
            tenant_id=ctx.tenant_id,
            workspace_id=ctx.workspace_id,
            message_id=message_id,
            sent_at=sent_at,
            channel=channel,
        )
    except SendBlocked as exc:
        status_code = 404 if exc.code == "NOT_FOUND" else 409
        raise HTTPException(
            status_code=status_code,
            detail={"code": exc.code, "detail": exc.detail},
        ) from None
    return {
        "message_id": str(message.id),
        "status": message.status,
        "sent_at": (
            message.sent_at.isoformat() if message.sent_at is not None else None
        ),
        "channel": (message.metadata or {}).get("channel", channel),
    }


# ``main`` includes this aggregate so the protected routes keep their service
# token while the Feishu callback stays exempt.
router = APIRouter()
router.include_router(protected_router)
router.include_router(callback_router)
