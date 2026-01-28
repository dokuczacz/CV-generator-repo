"""Job Reference Object (JRO) models.

Goal:
- Analyze a raw job offer text once.
- Persist only a normalized, compact reference object.
- Discard raw job offer text after analysis.

The schema is intentionally compact and ATS-oriented.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false


class JobReference(BaseModel):
    """Normalized job reference extracted from a job offer."""

    role_title: str = Field(..., description="Target role title")
    company: Optional[str] = Field(None, description="Company name, if explicitly present")
    location: Optional[str] = Field(None, description="Job location, if explicitly present")
    seniority: Optional[str] = Field(None, description="Seniority level (e.g. junior/mid/senior), if present")
    employment_type: Optional[str] = Field(None, description="Employment type (e.g. full-time/contract), if present")

    responsibilities: List[str] = Field(default_factory=list, description="Key responsibilities")
    must_haves: List[str] = Field(default_factory=list, description="Must-have requirements")
    nice_to_haves: List[str] = Field(default_factory=list, description="Nice-to-have requirements")

    tools_tech: List[str] = Field(default_factory=list, description="Tools/technologies mentioned")
    keywords: List[str] = Field(default_factory=list, description="ATS keywords and phrases")

    @validator("responsibilities", "must_haves", "nice_to_haves", "tools_tech", "keywords", pre=True)
    def _coerce_list(cls, v):  # type: ignore
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


JOB_REFERENCE_SCHEMA = {
    "name": "job_reference",
    "strict": True,
    "schema": enforce_additional_properties_false(JobReference.schema()),
}


def get_job_reference_response_format() -> dict:
    """OpenAI Responses API JSON schema format config.

    The OpenAI Python SDK (v2+) expects this object under `text={"format": ...}`.
    """

    return {"type": "json_schema", **JOB_REFERENCE_SCHEMA}


def parse_job_reference(response_json: str | dict) -> JobReference:
    """Parse and validate a job reference JSON payload."""

    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return JobReference.parse_obj(response_json)


def format_job_reference_for_display(job_ref: dict) -> str:
    """Best-effort, compact summary for UI display."""

    if not isinstance(job_ref, dict) or not job_ref:
        return "(no job reference)"

    title = str(job_ref.get("role_title") or "").strip() or "(unknown role)"
    company = str(job_ref.get("company") or "").strip()
    location = str(job_ref.get("location") or "").strip()

    header_parts = [p for p in [title, company, location] if p]
    lines: List[str] = [" | ".join(header_parts) if header_parts else title]

    def _bullets(key: str, label: str, max_items: int = 8) -> None:
        items = job_ref.get(key)
        if not isinstance(items, list) or not items:
            return
        cleaned = [str(x).strip() for x in items if str(x).strip()]
        if not cleaned:
            return
        head = cleaned[:max_items]
        lines.append(f"{label}: " + "; ".join(head) + ("; …" if len(cleaned) > max_items else ""))

    _bullets("must_haves", "Must-haves")
    _bullets("tools_tech", "Tools/tech")
    _bullets("keywords", "Keywords")

    return "\n".join(lines)
