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
    company_address: Optional[str] = Field(None, description="Company address, if explicitly present")
    company_email: Optional[str] = Field(None, description="Company contact email, if explicitly present")
    company_phone: Optional[str] = Field(None, description="Company contact phone, if explicitly present")
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


def _format_job_reference(
    job_ref: dict,
    *,
    section_caps: dict[str, int],
    include_sections: list[tuple[str, str]],
) -> str:
    if not isinstance(job_ref, dict) or not job_ref:
        return "(no job reference)"

    title = str(job_ref.get("role_title") or "").strip() or "(unknown role)"
    company = str(job_ref.get("company") or "").strip()
    location = str(job_ref.get("location") or "").strip()
    seniority = str(job_ref.get("seniority") or "").strip()
    employment_type = str(job_ref.get("employment_type") or "").strip()
    company_address = str(job_ref.get("company_address") or "").strip()
    company_email = str(job_ref.get("company_email") or "").strip()
    company_phone = str(job_ref.get("company_phone") or "").strip()

    header_parts = [p for p in [title, company, location] if p]
    lines: List[str] = [" | ".join(header_parts) if header_parts else title]

    meta_parts = [p for p in [seniority, employment_type] if p]
    if meta_parts:
        lines.append("Profile: " + " | ".join(meta_parts))

    company_info_parts = [
        ("Address", company_address),
        ("Email", company_email),
        ("Phone", company_phone),
    ]
    company_info = [f"{label}: {value}" for label, value in company_info_parts if value]
    if company_info:
        lines.append("Company prompt info: " + " | ".join(company_info))

    for key, label in include_sections:
        items = job_ref.get(key)
        if not isinstance(items, list) or not items:
            continue
        cleaned = [str(x).strip() for x in items if str(x).strip()]
        if not cleaned:
            continue
        cap = int(section_caps.get(key, 6))
        head = cleaned[:cap]
        suffix = "; ..." if len(cleaned) > cap else ""
        lines.append(f"{label}: " + "; ".join(head) + suffix)

    return "\n".join(lines)


def format_job_reference_for_display(job_ref: dict) -> str:
    """Best-effort, compact summary for UI display."""
    return _format_job_reference(
        job_ref,
        section_caps={"must_haves": 6, "tools_tech": 6, "keywords": 6},
        include_sections=[
            ("must_haves", "Must-haves"),
            ("tools_tech", "Tools/tech"),
            ("keywords", "Keywords"),
        ],
    )


def format_job_reference_for_prompt(job_ref: dict) -> str:
    """Richer deterministic summary for model input blocks."""
    return _format_job_reference(
        job_ref,
        section_caps={
            "responsibilities": 8,
            "must_haves": 8,
            "nice_to_haves": 5,
            "tools_tech": 8,
            "keywords": 8,
        },
        include_sections=[
            ("responsibilities", "Responsibilities"),
            ("must_haves", "Must-haves"),
            ("nice_to_haves", "Nice-to-haves"),
            ("tools_tech", "Tools/tech"),
            ("keywords", "Keywords"),
        ],
    )
