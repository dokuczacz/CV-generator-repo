"""Cover letter proposal models (structured output).

Design goals:
- Structured JSON for deterministic rendering + QA.
- No new facts: content must be grounded strictly in cv_data (and optional job_reference summary).
- Fixed structure; no bullets; word cap enforced by downstream validation.
"""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false


class CoverLetterHeaderProposal(BaseModel):
    """Header fields.

    Policy: the model must NOT invent contact/company details; the backend derives them.
    Therefore the model should return empty strings for these fields.
    """

    sender_name: str = Field("", description="(leave empty) backend derives from cv_data.full_name")
    sender_email: str = Field("", description="(leave empty) backend derives from cv_data.email")
    sender_phone: str = Field("", description="(leave empty) backend derives from cv_data.phone")
    sender_address: str = Field("", description="(leave empty) backend derives from cv_data.address_lines")
    date: str = Field("", description="(leave empty) backend sets current date")
    recipient_company: str = Field("", description="(leave empty) backend derives from job_reference.company when present")
    recipient_job_title: str = Field("", description="(leave empty) backend derives from job_reference.title when present")


class CoverLetterProposal(BaseModel):
    header: CoverLetterHeaderProposal = Field(..., description="Header fields (backend-derived; leave empty strings).")
    opening_paragraph: str = Field(..., description="Opening paragraph (2 sentences).")
    core_paragraphs: List[str] = Field(..., min_items=1, max_items=2, description="Core paragraphs (1–2).")
    closing_paragraph: str = Field(..., description="Closing paragraph (neutral).")
    signoff: str = Field(..., description="Formal sign-off in the target language, e.g. 'Kind regards' (EN), 'Mit freundlichen Grüßen' (DE), 'Z poważaniem' (PL), followed by '\\nName' (Name must match CV).")
    notes: str = Field("", description="Optional short explanation (max 500 chars).")

    @validator("opening_paragraph", "closing_paragraph", "signoff", pre=True)
    def _coerce_str(cls, v):  # type: ignore
        return "" if v is None else str(v)

    @validator("core_paragraphs", pre=True)
    def _coerce_core(cls, v):  # type: ignore
        if v is None:
            return []
        if isinstance(v, str):
            return [v]
        return v


COVER_LETTER_PROPOSAL_SCHEMA = {
    "name": "cover_letter_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(CoverLetterProposal.schema()),
}


def get_cover_letter_proposal_response_format() -> dict:
    return {"type": "json_schema", **COVER_LETTER_PROPOSAL_SCHEMA}


def parse_cover_letter_proposal(response_json: str | dict) -> CoverLetterProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return CoverLetterProposal.parse_obj(response_json)

