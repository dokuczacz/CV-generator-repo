"""IT/AI Skills and Technical/Operational Skills proposal models.

Goal:
- The model proposes filtered/ranked skill lists by job relevance.
- Two separate schemas: it_ai_skills and technical_operational_skills.
- Backend preserves structure for PDF rendering.
- Proposal must be fact-preserving (only filter/rank existing skills).
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .openai_json_schema import enforce_additional_properties_false


class SkillsProposal(BaseModel):
    """Proposed IT/AI skills section (filtered and ranked)."""

    skills: List[str] = Field(..., description="Filtered and ranked IT/AI skills (5-10 items max)")
    notes: str = Field("", description="Short explanation of what changed (no sensitive data)")


SKILLS_PROPOSAL_SCHEMA = {
    "name": "skills_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(SkillsProposal.schema()),
}


def get_skills_proposal_response_format() -> dict:
    return {"type": "json_schema", **SKILLS_PROPOSAL_SCHEMA}


def parse_skills_proposal(response_json: str | dict) -> SkillsProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return SkillsProposal.parse_obj(response_json)


class TechnicalOperationalSkillsProposal(BaseModel):
    """Proposed Technical/Operational skills section (filtered and ranked)."""

    skills: List[str] = Field(..., description="Filtered and ranked technical/operational skills (5-10 items max)")
    notes: str = Field("", description="Short explanation of what changed (no sensitive data)")


TECHNICAL_OPERATIONAL_SKILLS_PROPOSAL_SCHEMA = {
    "name": "technical_operational_skills_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(TechnicalOperationalSkillsProposal.schema()),
}


def get_technical_operational_skills_proposal_response_format() -> dict:
    return {"type": "json_schema", **TECHNICAL_OPERATIONAL_SKILLS_PROPOSAL_SCHEMA}


def parse_technical_operational_skills_proposal(response_json: str | dict) -> TechnicalOperationalSkillsProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return TechnicalOperationalSkillsProposal.parse_obj(response_json)
