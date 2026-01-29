"""Further experience (technical projects) proposal models.

Goal:
- The model proposes improved further_experience section (technical projects).
- Each project has title, organization, date_range, and bullets.
- Backend preserves structure for PDF rendering.
- Proposal must be fact-preserving (no invention).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false


class FurtherExperienceProjectProposal(BaseModel):
    """Proposed single technical project."""

    title: str = Field(..., description="Project title/role")
    organization: str = Field("", description="Organization/company name (if applicable)")
    date_range: str = Field("", description="Project period (e.g., '2023-01 – 2023-06')")
    location: str = Field("", description="City, Country (optional)")
    bullets: List[str] = Field(..., description="Achievement bullets for this project (1-3 bullets)")

    @validator("bullets", pre=True)
    def _coerce_bullets(cls, v):  # type: ignore
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


class FurtherExperienceProposal(BaseModel):
    """Proposed further experience section with project-by-project structure."""

    projects: List[FurtherExperienceProjectProposal] = Field(..., description="Proposed technical projects (1-3 most relevant)")
    notes: str = Field("", description="Short explanation of what changed (no sensitive data)")


FURTHER_EXPERIENCE_PROPOSAL_SCHEMA = {
    "name": "further_experience_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(FurtherExperienceProposal.schema()),
}


def get_further_experience_proposal_response_format() -> dict:
    return {"type": "json_schema", **FURTHER_EXPERIENCE_PROPOSAL_SCHEMA}


def parse_further_experience_proposal(response_json: str | dict) -> FurtherExperienceProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return FurtherExperienceProposal.parse_obj(response_json)
