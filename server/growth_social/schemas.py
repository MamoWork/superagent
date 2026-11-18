"""Pydantic models for the social intent scoring pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "IntentDimensionDraft",
    "IntentPenaltyDraft",
    "IntentScoreDraft",
    "IntentScore",
]


class IntentDimensionDraft(BaseModel):
    """One rubric dimension scored by the model."""

    dimension_id: str
    score: int = Field(ge=0, le=10)
    rationale: str = ""


class IntentPenaltyDraft(BaseModel):
    """One penalty suggested by the model.

    ``points`` is accepted from the model but is never trusted: the server
    replaces it with the rubric's authoritative value.
    """

    code: str
    points: int = Field(le=0)
    rationale: str = ""


class IntentScoreDraft(BaseModel):
    """Raw model output validated before the server computes a total."""

    dimensions: list[IntentDimensionDraft]
    penalties: list[IntentPenaltyDraft] = Field(default_factory=list)
    summary: str = ""


class IntentScore(BaseModel):
    """Server-authoritative intent score persisted on the lead."""

    score: int = Field(ge=0, le=100)
    status: Literal["qualified", "watch", "dropped"]
    dimensions: list[IntentDimensionDraft]
    penalties: list[IntentPenaltyDraft]
    summary: str = ""
