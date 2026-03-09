"""Unified CV + Cover Letter proposal models.

Used by experiment mode `variant_unified` where CV tailoring and cover letter are generated in one model call.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .combined_cv_proposal import CombinedCVProposal
from .cover_letter_proposal import CoverLetterProposal
from .openai_json_schema import enforce_additional_properties_false


class UnifiedCVCLProposal(BaseModel):
    combined_cv: CombinedCVProposal = Field(..., description="Combined CV proposal block")
    cover_letter: CoverLetterProposal = Field(..., description="Cover letter proposal block")
    alignment_notes: str = Field(
        ...,
        min_length=1,
        description="Required note describing grounding and positioning alignment (E0-only)",
    )


UNIFIED_CV_CL_PROPOSAL_SCHEMA = {
    "name": "unified_cv_cl_proposal",
    "strict": True,
    "schema": enforce_additional_properties_false(UnifiedCVCLProposal.schema()),
}


def get_unified_cv_cl_proposal_response_format() -> dict:
    return {"type": "json_schema", **UNIFIED_CV_CL_PROPOSAL_SCHEMA}


def parse_unified_cv_cl_proposal(response_json: str | dict) -> UnifiedCVCLProposal:
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)
    return UnifiedCVCLProposal.parse_obj(response_json)
