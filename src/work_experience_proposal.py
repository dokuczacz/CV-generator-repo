"""Work experience proposal (diff-only) models.

Goal:
- The model proposes improved bullets for exactly one role.
- Backend decides whether to apply; user must explicitly accept.
- Proposal must be fact-preserving (no invention).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false


class WorkExperienceBulletsProposal(BaseModel):
    """Proposed bullet list for a single work experience entry."""

    proposed_bullets: List[str] = Field(..., description="Proposed bullets for this role")
    notes: str = Field("", description="Short explanation of what changed (no sensitive data)")

    @validator("proposed_bullets", pre=True)
    def _coerce_bullets(cls, v):  # type: ignore
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA = {
    "name": "work_experience_bullets_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(WorkExperienceBulletsProposal.schema()),
}


def get_work_experience_bullets_proposal_response_format() -> dict:
    return {"type": "json_schema", **WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA}


def parse_work_experience_bullets_proposal(response_json: str | dict) -> WorkExperienceBulletsProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return WorkExperienceBulletsProposal.parse_obj(response_json)
