"""Task handlers and adapter wiring for the social pipeline.

``build_social_router`` registers one handler per pipeline task type; each
handler delegates to its standalone service. Payload lookups are deliberately
not defensive: a missing key or malformed UUID raises, and
``growth_core.services.worker.run_once`` records the failure on the task.

``build_social_adapters`` resolves provider configs and enabled sources into an
:class:`AdapterRegistry` and a ``source_type -> adapter`` mapping. A source
type with no configured provider raises at startup rather than being skipped.

This module does not import adapter modules for their registration side
effects; the composition roots (``growth_social.worker`` and
``growth_social.asgi``) own that.
"""

from __future__ import annotations

from uuid import UUID

from growth_core.adapters.base import LLMClient, Notifier, SourceAdapter
from growth_core.adapters.registry import AdapterRegistry, EnvSecretResolver
from growth_core.config import GrowthSettings
from growth_core.repositories.base import GrowthRepository
from growth_core.services.worker import TaskRouter
from growth_social.services.drafting import draft_reply
from growth_social.services.followup import process_followup_check
from growth_social.services.ingest import ingest_social
from growth_social.services.scoring import score_lead

__all__ = ["build_social_adapters", "build_social_router"]


def build_social_router(
    *,
    repo: GrowthRepository,
    adapters: dict[str, SourceAdapter],
    notifier: Notifier | None,
    llm: LLMClient,
    settings: GrowthSettings,
) -> TaskRouter:
    """Register the four social task handlers on a fresh :class:`TaskRouter`."""
    router = TaskRouter()

    async def handle_ingest(task) -> None:
        await ingest_social(
            repo,
            adapters,
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
        )

    async def handle_score(task) -> None:
        await score_lead(
            repo,
            llm,
            tenant_id=task.tenant_id,
            lead_id=UUID(task.payload["lead_id"]),
            model=settings.llm_scoring_model,
        )

    async def handle_draft(task) -> None:
        await draft_reply(
            repo,
            llm,
            notifier,
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            lead_id=UUID(task.payload["lead_id"]),
            settings=settings,
        )

    async def handle_followup(task) -> None:
        await process_followup_check(
            repo,
            llm,
            notifier,
            tenant_id=task.tenant_id,
            workspace_id=task.workspace_id,
            original_message_id=UUID(task.payload["original_message_id"]),
            settings=settings,
        )

    router.register("social.ingest", handle_ingest)
    router.register("social.score", handle_score)
    router.register("social.draft", handle_draft)
    router.register("social.followup_check", handle_followup)
    return router


async def build_social_adapters(
    repo: GrowthRepository, settings: GrowthSettings
) -> tuple[AdapterRegistry, dict[str, SourceAdapter]]:
    """Build the registry and the enabled ``source_type -> adapter`` mapping.

    Adapter factories must already be registered (the composition roots import
    the adapter modules). Every enabled source must resolve to a configured
    provider; a missing one raises ``ProviderNotConfigured`` at startup.
    """
    tenant_id = UUID(settings.tenant_id)
    configs = await repo.list_provider_configs(tenant_id, "social_source")
    registry = AdapterRegistry(configs, EnvSecretResolver())
    sources = await repo.list_enabled_sources(tenant_id)
    adapters = {
        source.source_type: registry.source(source.source_type)
        for source in sources
    }
    return registry, adapters
