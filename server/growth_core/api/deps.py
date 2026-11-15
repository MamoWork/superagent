"""Shared request authentication and context dependencies."""

from __future__ import annotations

import hmac
from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException, Request

_INVALID_TENANT = {"code": "INVALID_TENANT_ID"}
_INVALID_WORKSPACE = {"code": "INVALID_WORKSPACE_ID"}


@dataclass(frozen=True)
class RequestContext:
    """Tenant/workspace scope plus the caller-supplied idempotency key."""

    tenant_id: UUID
    workspace_id: UUID
    idempotency_key: str | None


def _tokens_match(expected: str, supplied: str) -> bool:
    """Constant-time service-token comparison that fails closed on empty input."""
    if not expected or not supplied:
        return False
    try:
        return hmac.compare_digest(
            expected.encode("utf-8"), supplied.encode("utf-8")
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return False


async def require_service_token(request: Request) -> None:
    """Reject requests that do not present the configured service token.

    The token is never echoed or logged. An empty configured token disables
    access entirely rather than accepting an empty header.
    """
    expected = request.app.state.settings.service_token
    supplied = request.headers.get("x-service-token", "")
    if not _tokens_match(expected, supplied):
        raise HTTPException(status_code=401, detail="invalid service token")


def _parse_uuid(value: str, detail: dict[str, str]) -> UUID:
    try:
        return UUID(value)
    except (AttributeError, TypeError, ValueError):
        raise HTTPException(status_code=400, detail=detail) from None


def get_context(request: Request) -> RequestContext:
    """Resolve the request's tenant/workspace scope and idempotency key.

    ``X-Tenant-Id`` and ``X-Workspace-Id`` override the configured defaults
    when present. Invalid values are rejected with a structured 400.
    """
    settings = request.app.state.settings

    tenant_value = request.headers.get("x-tenant-id")
    if tenant_value is None:
        tenant_value = settings.tenant_id
    workspace_value = request.headers.get("x-workspace-id")
    if workspace_value is None:
        workspace_value = settings.workspace_id

    return RequestContext(
        tenant_id=_parse_uuid(tenant_value, _INVALID_TENANT),
        workspace_id=_parse_uuid(workspace_value, _INVALID_WORKSPACE),
        idempotency_key=request.headers.get("idempotency-key") or None,
    )
