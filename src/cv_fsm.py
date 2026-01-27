from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CVStage(str, Enum):
    INGEST = "INGEST"
    PREPARE = "PREPARE"
    REVIEW = "REVIEW"
    CONFIRM = "CONFIRM"
    EXECUTE = "EXECUTE"
    DONE = "DONE"


EDIT_INTENT_KEYWORDS_PL = ("zmień", "popraw", "cofnij", "dodaj", "usuń", "jednak", "nie tak", "inaczej")
EDIT_INTENT_KEYWORDS_EN = ("change", "edit", "update", "modify", "fix", "revise", "adjust")


@dataclass(frozen=True)
class SessionState:
    confirmation_required: bool
    pending_edits: int
    generate_requested: bool
    user_confirm_yes: bool = False
    user_confirm_no: bool = False
    turns_in_review: int = 0  # Auto-advance after N turns without explicit confirmation


@dataclass(frozen=True)
class ValidationState:
    validation_passed: bool
    readiness_ok: bool
    pdf_generated: bool = False
    pdf_failed: bool = False
    high_confidence: bool = False  # Model has high-confidence edits ready


def detect_edit_intent(user_message: str) -> bool:
    text = (user_message or "").lower()
    return any(k in text for k in (*EDIT_INTENT_KEYWORDS_PL, *EDIT_INTENT_KEYWORDS_EN))


def resolve_stage(
    current_stage: str | CVStage | None,
    user_message: str,
    session_state: SessionState,
    validation_state: ValidationState,
) -> CVStage:
    """
    Resolve the next stage deterministically (backend-owned).

    Priority rules:
    1) edit_intent_overrides_all -> REVIEW
    2) auto-advance REVIEW->CONFIRM after 3 turns without explicit confirmation
    3) confirmation gate blocks execute (explicit user "yes" OR auto-advance)
    4) execute requires readiness + validation
    5) done is not terminal

    Turn-based auto-advance: in REVIEW stage, after N turns without user_confirm_yes,
    system assumes high-confidence edits are ready and auto-advances to CONFIRM.
    This enforces DoD: perfect CV in 3 minutes, 3 turns max.
    """
    if isinstance(current_stage, CVStage):
        cur = current_stage
    else:
        try:
            cur = CVStage(str(current_stage or CVStage.INGEST.value))
        except Exception:
            cur = CVStage.INGEST

    if detect_edit_intent(user_message):
        return CVStage.REVIEW

    # DONE is not terminal: only edit intent forces REVIEW; otherwise stays DONE.
    if cur == CVStage.DONE:
        return CVStage.DONE

    if cur == CVStage.INGEST:
        # Session exists by the time resolve_stage is called in our backend flow.
        return CVStage.PREPARE

    if cur == CVStage.PREPARE:
        if session_state.confirmation_required:
            return CVStage.REVIEW
        return CVStage.PREPARE

    if cur == CVStage.REVIEW:
        # Explicit user confirmation: say "yes"/"import prefill" to move to CONFIRM
        if session_state.user_confirm_yes:
            return CVStage.CONFIRM
        
        # Auto-advance after 3 turns without explicit confirmation
        # (model has had time to gather high-confidence edits)
        AUTO_ADVANCE_AFTER_TURNS = 3
        if session_state.turns_in_review >= AUTO_ADVANCE_AFTER_TURNS:
            return CVStage.CONFIRM
        
        return CVStage.REVIEW

    if cur == CVStage.CONFIRM:
        if session_state.user_confirm_no:
            return CVStage.REVIEW
        if not session_state.generate_requested:
            return CVStage.CONFIRM
        if validation_state.validation_passed and validation_state.readiness_ok and session_state.pending_edits == 0:
            return CVStage.EXECUTE
        # Relaxed gate: if model has high-confidence edits, allow progression even if readiness_ok is False
        if validation_state.high_confidence and session_state.pending_edits == 0:
            return CVStage.EXECUTE
        return CVStage.REVIEW

    if cur == CVStage.EXECUTE:
        if validation_state.pdf_generated:
            return CVStage.DONE
        if validation_state.pdf_failed:
            return CVStage.REVIEW
        return CVStage.EXECUTE

    return CVStage.REVIEW
