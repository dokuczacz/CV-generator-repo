"""Unified skills proposal model (IT & AI + Technical & Operational in one response).

Goal:
- Single OpenAI call produces both skill sections.
- Ensures consistency across both sections (no duplication, complementary).
- Schema-driven: response must validate as JSON.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .openai_json_schema import enforce_additional_properties_false


class SkillsUnifiedProposal(BaseModel):
    """Unified skills proposal: IT & AI skills + Technical & Operational skills."""

    it_ai_skills: List[str] = Field(
        ...,
        description="IT & AI skills: digital tools, automation, AI usage, data-driven systems, reporting (5-8 items)",
    )
    technical_operational_skills: List[str] = Field(
        ...,
        description="Technical & Operational skills: quality systems, process improvement, project delivery, production, construction, operational governance (5-8 items)",
    )
    notes: str = Field(
        "",
        description="Short explanation of what changed or how sections complement each other (no sensitive data, max 500 chars)",
    )


SKILLS_UNIFIED_PROPOSAL_SCHEMA = {
    "name": "skills_unified_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(SkillsUnifiedProposal.schema()),
}


def get_skills_unified_proposal_response_format() -> dict:
    return {"type": "json_schema", **SKILLS_UNIFIED_PROPOSAL_SCHEMA}


def parse_skills_unified_proposal(response_json: str | dict) -> SkillsUnifiedProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return SkillsUnifiedProposal.parse_obj(response_json)
