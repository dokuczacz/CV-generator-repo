"""Combined CV tailoring proposal models.

Used by experiment mode `variant_split` where work + skills are generated in one model call.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false
from .work_experience_proposal import WorkExperienceRoleProposal


class CombinedCVProposal(BaseModel):
    """Combined CV output: work roles + skill blocks."""

    roles: List[WorkExperienceRoleProposal] = Field(..., description="Tailored work experience roles")
    it_ai_skills: List[str] = Field(..., min_items=1, max_items=12, description="IT/AI skills list")
    technical_operational_skills: List[str] = Field(
        ...,
        min_items=1,
        max_items=12,
        description="Technical and operational skills list",
    )
    notes: str = Field("", description="Short explanation of changes")

    @validator("it_ai_skills", "technical_operational_skills", pre=True)
    def _coerce_list(cls, v):  # type: ignore
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


COMBINED_CV_PROPOSAL_SCHEMA = {
    "name": "combined_cv_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(CombinedCVProposal.schema()),
}


def get_combined_cv_proposal_response_format() -> dict:
    return {"type": "json_schema", **COMBINED_CV_PROPOSAL_SCHEMA}


def parse_combined_cv_proposal(response_json: str | dict) -> CombinedCVProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return CombinedCVProposal.parse_obj(response_json)
