"""
Structured response models for CV Generator.

Based on OpenAI Structured Outputs best practices:
https://cookbook.openai.com/examples/structured_outputs_intro
https://learn.microsoft.com/en-us/azure/ai-foundry/openai/how-to/structured-outputs
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field, validator

from .openai_json_schema import enforce_additional_properties_false


class ResponseType(str, Enum):
    """High-level category of response for UI routing."""

    QUESTION = "question"
    PROPOSAL = "proposal"
    CONFIRMATION = "confirmation"
    STATUS_UPDATE = "status_update"
    ERROR = "error"
    COMPLETION = "completion"


class SectionType(str, Enum):
    """Type of content section in multi-part message."""

    INFO = "info"
    WARNING = "warning"
    SUCCESS = "success"
    QUESTION = "question"
    PROPOSAL = "proposal"


class MessageSection(BaseModel):
    """Organized content section within a message."""

    title: str = Field(..., description="Section title")
    content: str = Field(..., description="Section content (markdown supported)")
    type: SectionType = Field(..., description="Section type for UI styling")


class Question(BaseModel):
    """Clarifying question with multiple choice options."""

    id: str = Field(..., description="Unique question identifier")
    question: str = Field(..., description="Question text")

    # Some model outputs omit options or send null; normalize to empty list to avoid hard fails.
    options: List[str] = Field(default_factory=list, description="Available answer choices")

    @validator("options", pre=True)
    def _coerce_options(cls, v):  # type: ignore
        if v is None:
            return []
        return v


class UserMessage(BaseModel):
    """Content displayed to user in chat interface."""

    text: str = Field(..., description="Primary message text (markdown supported)")
    sections: List[MessageSection] = Field(
        default_factory=list, description="Organized content sections (optional, for multi-part messages)"
    )
    questions: List[Question] = Field(default_factory=list, description="Clarifying questions for user (if response_type=question)")

    @validator("sections", pre=True)
    def _coerce_sections(cls, v):  # type: ignore
        if v is None:
            return []
        return v

    @validator("questions", pre=True)
    def _coerce_questions(cls, v):  # type: ignore
        if v is None:
            return []
        return v


class Confidence(str, Enum):
    """Model confidence level."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ValidationStatus(BaseModel):
    """Current CV validation state."""

    schema_valid: bool = Field(..., description="Whether CV schema is valid")
    page_count_ok: bool = Field(..., description="Whether page count is acceptable")
    required_fields_present: bool = Field(..., description="Whether all required fields are present")
    issues: List[str] = Field(default_factory=list, description="Validation issues/warnings")

    @validator("issues", pre=True)
    def _coerce_issues(cls, v):  # type: ignore
        if v is None:
            return []
        return v


class ResponseMetadata(BaseModel):
    """Response metadata for tracking and debugging."""

    response_id: str = Field(..., description="Unique response identifier")
    timestamp: str = Field(..., description="Response timestamp (ISO 8601)")
    model_reasoning: str = Field(..., description="Brief explanation of decision-making process")
    confidence: Confidence = Field(..., description="Model's confidence in this response")
    validation_status: ValidationStatus = Field(..., description="Current CV validation state")


class ToolName(str, Enum):
    """Available tool names for system actions."""

    UPDATE_CV_FIELD = "update_cv_field"
    VALIDATE_CV = "validate_cv"
    GENERATE_CV_FROM_SESSION = "generate_cv_from_session"
    GET_CV_SESSION = "get_cv_session"
    GET_PDF_BY_REF = "get_pdf_by_ref"
    EXPORT_SESSION_DEBUG = "export_session_debug"


class ToolCall(BaseModel):
    """Tool call specification."""

    tool_name: ToolName = Field(..., description="Name of tool to call")
    parameters: dict = Field(..., description="Tool-specific parameters")
    reason: str = Field(..., description="Why this tool is needed")


class SystemActions(BaseModel):
    """System actions for backend execution."""

    tool_calls: List[ToolCall] = Field(default_factory=list, description="Tool calls to execute (max 4)")
    confirmation_required: bool = Field(False, description="Whether user confirmation is required before executing")

    @validator("tool_calls", pre=True)
    def _coerce_tool_calls(cls, v):  # type: ignore
        if v is None:
            return []
        return v


class CVAssistantResponse(BaseModel):
    """
    Structured response from CV assistant with strict schema enforcement.

    This model ensures:
    - Clear separation between user-facing content and system metadata
    - Multi-section responses for complex interactions
    - Validation status tracking
    - Safety-based refusal handling
    """

    response_type: ResponseType = Field(..., description="High-level category of response for UI routing")
    user_message: UserMessage = Field(..., description="Content displayed to user in chat interface")
    system_actions: SystemActions = Field(default_factory=SystemActions, description="System actions for backend execution")
    metadata: ResponseMetadata = Field(..., description="Response metadata for tracking and debugging")
    refusal: Optional[str] = Field(None, description="Safety-based refusal message (null if no refusal)")

    @validator("system_actions", pre=True, always=True)
    def _ensure_system_actions(cls, v):  # type: ignore
        """Ensure system_actions is always a valid SystemActions object, even if None."""
        if v is None:
            return SystemActions()
        return v


# JSON Schema export for OpenAI API
CV_ASSISTANT_RESPONSE_SCHEMA = {
    "name": "cv_assistant_response",
    "strict": True,
    "schema": enforce_additional_properties_false(CVAssistantResponse.schema()),
}


def get_response_format() -> dict:
    """
    Get response_format parameter for OpenAI API call.

    Usage:
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[...],
            response_format=get_response_format()
        )
    """
    # OpenAI Python SDK (v2+) expects this object under `text={"format": ...}` for the Responses API.
    return {"type": "json_schema", **CV_ASSISTANT_RESPONSE_SCHEMA}


def parse_structured_response(response_json: str | dict) -> CVAssistantResponse:
    """
    Parse and validate structured response from model.

    Args:
        response_json: Raw JSON string or dict from model

    Returns:
        Validated CVAssistantResponse object

    Raises:
        ValidationError: If response doesn't match schema
    """
    if isinstance(response_json, str):
        import json

        response_json = json.loads(response_json)

    return CVAssistantResponse.parse_obj(response_json)


def format_user_message_for_ui(response: CVAssistantResponse) -> dict:
    """
    Format user_message for UI display.

    Returns:
        {
            "text": "Main message",
            "sections": [...],
            "questions": [...],
            "response_type": "question|proposal|..."
        }
    """
    return {
        "text": response.user_message.text,
        "sections": [{"title": s.title, "content": s.content, "type": s.type.value} for s in response.user_message.sections],
        "questions": [{"id": q.id, "question": q.question, "options": q.options} for q in response.user_message.questions],
        "response_type": response.response_type.value,
    }
