from src.cv_fsm import CVStage, SessionState, ValidationState, resolve_stage


def test_any_edit_forces_review():
    nxt = resolve_stage(
        CVStage.EXECUTE,
        "zmień doświadczenie",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=True),
        ValidationState(validation_passed=True, readiness_ok=True),
    )
    assert nxt == CVStage.REVIEW


def test_cannot_execute_without_readiness():
    nxt = resolve_stage(
        CVStage.CONFIRM,
        "generate pdf",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=True),
        ValidationState(validation_passed=False, readiness_ok=False),
    )
    assert nxt == CVStage.REVIEW


def test_happy_path_to_pdf_then_done():
    nxt = resolve_stage(
        CVStage.CONFIRM,
        "generate pdf",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=True),
        ValidationState(validation_passed=True, readiness_ok=True),
    )
    assert nxt == CVStage.EXECUTE
    nxt2 = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=False),
        ValidationState(validation_passed=True, readiness_ok=True, pdf_generated=True),
    )
    assert nxt2 == CVStage.DONE


def test_pdf_failure_returns_to_review():
    nxt = resolve_stage(
        CVStage.EXECUTE,
        "",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=False),
        ValidationState(validation_passed=True, readiness_ok=True, pdf_failed=True),
    )
    assert nxt == CVStage.REVIEW


def test_edit_after_done_returns_to_review():
    nxt = resolve_stage(
        CVStage.DONE,
        "dodaj certyfikat",
        SessionState(confirmation_required=False, pending_edits=0, generate_requested=False),
        ValidationState(validation_passed=True, readiness_ok=True),
    )
    assert nxt == CVStage.REVIEW

