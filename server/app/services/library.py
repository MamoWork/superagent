from __future__ import annotations

from app.db import Database, utcnow
from app.schemas import OpportunityAnalysis, SavedOpportunity


class LibraryRunNotFound(Exception):
    pass


class LibraryAnalysisMissing(Exception):
    pass


def save_opportunity(
    db: Database,
    run_id: str,
    *,
    stage: str = "saved",
    notes: str = "",
) -> SavedOpportunity:
    run = db.get_run(run_id)
    if run is None:
        raise LibraryRunNotFound(run_id)
    analysis_data = db.get_analysis(run_id)
    if analysis_data is None:
        raise LibraryAnalysisMissing(run_id)

    analysis = OpportunityAnalysis(**analysis_data)
    now = utcnow()
    existing = db.get_saved_opportunity(run_id)
    created_at = existing["created_at"] if existing else now
    opportunity = SavedOpportunity(
        run_id=run_id,
        direction=run["direction"],
        domain_pack=run["domain_pack"],
        title=analysis.one_liner or run["direction"],
        one_liner=analysis.one_liner,
        thesis=analysis.thesis,
        score=analysis.score,
        verdict=analysis.verdict,
        target_customer=analysis.target_customer,
        willingness_to_pay=analysis.willingness_to_pay,
        risks=analysis.risks,
        next_actions=analysis.next_actions,
        dimension_scores=analysis.dimension_scores,
        citations=analysis.citations,
        stage=stage,  # type: ignore[arg-type]
        notes=notes,
        created_at=created_at,
        updated_at=now,
    )
    db.upsert_saved_opportunity(
        run_id,
        stage=stage,
        notes=notes,
        verdict=analysis.verdict,
        score=analysis.score,
        direction=run["direction"],
        payload=opportunity.model_dump(mode="json"),
        created_at=created_at,
        updated_at=now,
    )
    return opportunity


def list_saved(db: Database) -> list[SavedOpportunity]:
    return [SavedOpportunity(**item) for item in db.list_saved_opportunities()]


def get_saved(db: Database, run_id: str) -> SavedOpportunity | None:
    item = db.get_saved_opportunity(run_id)
    return SavedOpportunity(**item) if item else None


def update_saved(
    db: Database,
    run_id: str,
    *,
    stage: str | None = None,
    notes: str | None = None,
) -> SavedOpportunity | None:
    existing = db.get_saved_opportunity(run_id)
    if existing is None:
        return None
    fields: dict[str, object] = {}
    if stage is not None:
        fields["stage"] = stage
    if notes is not None:
        fields["notes"] = notes
    if fields:
        db.update_saved_opportunity(run_id, **fields)
    updated = db.get_saved_opportunity(run_id)
    return SavedOpportunity(**updated) if updated else None


def delete_saved(db: Database, run_id: str) -> bool:
    return db.delete_saved_opportunity(run_id)
