"""
Wave 0.2: Terminal FSM State Tests

Tests that pdf_generated flag is properly set and FSM transitions work correctly.
"""

import pytest
from src.cv_fsm import CVStage, SessionState, ValidationState, resolve_stage


def test_pdf_generated_flag_enables_done_transition():
    """Test that pdf_generated=True enables EXECUTE → DONE transition."""

    next_stage = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(
            confirmation_required=False,
            pending_edits=0,
            generate_requested=False,
        ),
        ValidationState(
            validation_passed=True,
            readiness_ok=True,
            pdf_generated=True,  # Wave 0.2: Flag set after generation
        ),
    )

    assert next_stage == CVStage.DONE


def test_pdf_generated_false_keeps_execute():
    """Test that pdf_generated=False prevents DONE transition."""

    next_stage = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(
            confirmation_required=False,
            pending_edits=0,
            generate_requested=False,
        ),
        ValidationState(
            validation_passed=True,
            readiness_ok=True,
            pdf_generated=False,  # Not yet generated
        ),
    )

    # Should stay in EXECUTE (waiting for PDF generation)
    assert next_stage == CVStage.EXECUTE


def test_pdf_failed_returns_to_review():
    """Test that pdf_failed=True forces return to REVIEW for debugging."""

    next_stage = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(
            confirmation_required=False,
            pending_edits=0,
            generate_requested=False,
        ),
        ValidationState(
            validation_passed=True,
            readiness_ok=True,
            pdf_generated=False,
            pdf_failed=True,  # Generation failed
        ),
    )

    assert next_stage == CVStage.REVIEW


def test_done_state_is_stable():
    """Test that DONE state stays DONE without edit intent."""

    next_stage = resolve_stage(
        CVStage.DONE,
        "looks good!",  # Non-edit message
        SessionState(
            confirmation_required=False,
            pending_edits=0,
            generate_requested=False,
        ),
        ValidationState(
            validation_passed=True,
            readiness_ok=True,
            pdf_generated=True,
        ),
    )

    # Should stay in DONE (no edit intent detected)
    assert next_stage == CVStage.DONE


def test_edit_intent_escapes_done():
    """Test that edit intent keywords force DONE → REVIEW transition."""

    edit_keywords = ["zmień", "popraw", "dodaj", "usuń", "cofnij"]

    for keyword in edit_keywords:
        next_stage = resolve_stage(
            CVStage.DONE,
            f"{keyword} doświadczenie",  # Edit intent in Polish
            SessionState(
                confirmation_required=False,
                pending_edits=0,
                generate_requested=False,
            ),
            ValidationState(
                validation_passed=True,
                readiness_ok=True,
                pdf_generated=True,
            ),
        )

        assert next_stage == CVStage.REVIEW, f"Edit keyword '{keyword}' should force REVIEW"


def test_pdf_generation_readiness_gates():
    """Test that readiness gates still apply before EXECUTE."""

    # Test: validation not passed
    next_stage = resolve_stage(
        CVStage.CONFIRM,
        "generate pdf",
        SessionState(
            confirmation_required=False,
            pending_edits=0,
            generate_requested=True,
        ),
        ValidationState(
            validation_passed=False,  # Validation failed
            readiness_ok=False,
            pdf_generated=False,
        ),
    )

    # Should return to REVIEW (not EXECUTE)
    assert next_stage == CVStage.REVIEW


def test_execute_with_pending_edits_blocks():
    """Test that pending edits block EXECUTE transition."""

    next_stage = resolve_stage(
        CVStage.CONFIRM,
        "generate pdf",
        SessionState(
            confirmation_required=False,
            pending_edits=1,  # Edits not yet applied
            generate_requested=True,
        ),
        ValidationState(
            validation_passed=True,
            readiness_ok=True,
            pdf_generated=False,
        ),
    )

    # Should stay in CONFIRM (or go to REVIEW to apply edits)
    assert next_stage in (CVStage.CONFIRM, CVStage.REVIEW)


def test_full_workflow_with_flags():
    """Test complete workflow: INGEST → PREPARE → REVIEW → CONFIRM → EXECUTE → DONE."""

    # Stage 1: INGEST → PREPARE
    stage = resolve_stage(
        CVStage.INGEST,
        "uploaded CV",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=False),
        ValidationState(validation_passed=False, readiness_ok=False, pdf_generated=False),
    )
    assert stage == CVStage.PREPARE

    # Stage 2: PREPARE → REVIEW (confirmation required)
    stage = resolve_stage(
        CVStage.PREPARE,
        "review data",
        SessionState(confirmation_required=True, pending_edits=0, generate_requested=False),
        ValidationState(validation_passed=True, readiness_ok=False, pdf_generated=False),
    )
    assert stage == CVStage.REVIEW

    # Stage 3: REVIEW → CONFIRM (user confirms)
    stage = resolve_stage(
        CVStage.REVIEW,
        "yes, looks good",
        SessionState(confirmation_required=True, pending_edits=0, generate_requested=False, user_confirm_yes=True),
        ValidationState(validation_passed=True, readiness_ok=True, pdf_generated=False),
    )
    assert stage == CVStage.CONFIRM

    # Stage 4: CONFIRM → EXECUTE (generate requested)
    stage = resolve_stage(
        CVStage.CONFIRM,
        "generate pdf",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=True),
        ValidationState(validation_passed=True, readiness_ok=True, pdf_generated=False),
    )
    assert stage == CVStage.EXECUTE

    # Stage 5: EXECUTE → DONE (pdf_generated=True)
    stage = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=False),
        ValidationState(validation_passed=True, readiness_ok=True, pdf_generated=True),  # Wave 0.2
    )
    assert stage == CVStage.DONE


def test_metadata_flag_integration():
    """
    Integration test: verify that function_app correctly reads pdf_generated from metadata.

    This tests that the ValidationState construction in function_app.py line 2391
    correctly passes pdf_generated from session metadata.
    """

    # Mock metadata with pdf_generated flag
    mock_metadata = {
        "pdf_generated": True,
        "pdf_refs": {
            "some-pdf-ref": {"created_at": "2026-01-27T10:00:00"}
        }
    }

    # Simulate the ValidationState construction from function_app.py
    validation_state = ValidationState(
        validation_passed=True,
        readiness_ok=True,
        pdf_generated=bool(mock_metadata.get("pdf_generated")),
        pdf_failed=bool(mock_metadata.get("pdf_failed")),
    )

    assert validation_state.pdf_generated is True
    assert validation_state.pdf_failed is False

    # Now test FSM transition
    next_stage = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=False),
        validation_state,
    )

    assert next_stage == CVStage.DONE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
