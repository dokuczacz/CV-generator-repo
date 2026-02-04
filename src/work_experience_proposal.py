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
    bullets: List[str] = Field(
        ...,
        min_items=3,
        max_items=4,
        description="Achievement bullets for this role (3-4 bullets)",
    )

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

# Enforce hard max at schema-level so proposals never fail post-parse validation.
_BULLET_MAXLEN_HARD = 200


def _apply_bullet_max_length(schema: dict, *, max_len: int) -> dict:
    """Inject maxLength into any schema location that represents `bullets: string[]`."""
    def _walk(node: object) -> None:
        if isinstance(node, dict):
            props = node.get("properties")
            if isinstance(props, dict) and isinstance(props.get("bullets"), dict):
                bullets = props.get("bullets")
                if isinstance(bullets, dict):
                    items = bullets.get("items")
                    if isinstance(items, dict) and items.get("type") == "string":
                        items["maxLength"] = int(max_len)
                    elif isinstance(items, list):
                        for it in items:
                            if isinstance(it, dict) and it.get("type") == "string":
                                it["maxLength"] = int(max_len)
            for v in node.values():
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)

    try:
        _walk(schema)
    except Exception:
        pass
    return schema


# Mutate the schema dict in-place (module-level constant) safely.
WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA["schema"] = _apply_bullet_max_length(
    WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA["schema"],
    max_len=_BULLET_MAXLEN_HARD,
)


def get_work_experience_bullets_proposal_response_format() -> dict:
    return {"type": "json_schema", **WORK_EXPERIENCE_BULLETS_PROPOSAL_SCHEMA}


def parse_work_experience_bullets_proposal(response_json: str | dict) -> WorkExperienceBulletsProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return WorkExperienceBulletsProposal.parse_obj(response_json)
