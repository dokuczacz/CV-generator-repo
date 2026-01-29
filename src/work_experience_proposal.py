"""Work experience proposal (job-by-job) models.

Goal:
- The model proposes improved work_experience section with explicit role structure.
- Each job has title, company, date_range, and bullets.
- Backend preserves structure for PDF rendering.
- Proposal must be fact-preserving (no invention).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false


class WorkExperienceRoleProposal(BaseModel):
    """Proposed single work experience role."""

    title: str = Field(..., description="Job title/position")
    company: str = Field(..., description="Company/employer name")
    date_range: str = Field(..., description="Employment period (e.g., '2020-01 – 2025-04')")
    location: str = Field("", description="City, Country (optional)")
    bullets: List[str] = Field(..., description="Achievement bullets for this role (2-4 bullets)")

    @validator("bullets", pre=True)
    def _coerce_bullets(cls, v):  # type: ignore
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class WorkExperienceBulletsProposal(BaseModel):
    """Proposed work experience section with role-by-role structure."""

    roles: List[WorkExperienceRoleProposal] = Field(..., description="Proposed work experience roles (3-4 most recent/relevant)")
    notes: str = Field("", description="Short explanation of what changed (no sensitive data)")


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
