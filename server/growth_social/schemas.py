"""Pydantic models for the social intent scoring pipeline."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

__all__ = [
    "IntentDimensionDraft",
    "IntentPenaltyDraft",
    "IntentScoreDraft",
    "IntentScore",
    "ReplyDraft",
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


class ReplyDraft(BaseModel):
    """Raw model output for a proposed reply.

    The server owns the ``{{LINK}}`` policy: a draft must contain exactly one
    placeholder, but that is checked by the drafting service rather than here
    so a policy failure becomes a recorded rejection, not an LLM error.
    """

    body_markdown: str
    link_path: str
    risk_flags: list[str] = Field(default_factory=list)
