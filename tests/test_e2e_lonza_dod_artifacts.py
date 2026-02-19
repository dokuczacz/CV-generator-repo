from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import pytest
import requests

from function_app import _looks_like_job_posting_text


BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:7071")
SCENARIO_PATH = Path("docs/scenarios/scenario_2ec0fd55.json")
SAMPLE_DOCX_PATH = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
ARTIFACT_DIR = Path("artifacts/e2e")


def _env_int(name: str, default: int) -> int:
    raw = str(os.environ.get(name, "")).strip()
    if not raw:
        return default
    try:
        value = int(raw)
        return value if value > 0 else default
    except Exception:
        return default


E2E_REQUEST_TIMEOUT_SEC = _env_int("E2E_REQUEST_TIMEOUT_SEC", 90)
E2E_MAX_FLOW_SECONDS = _env_int("E2E_MAX_FLOW_SECONDS", 480)
E2E_MAX_STEPS = _env_int("E2E_MAX_STEPS", 60)
E2E_MAX_COVER_ATTEMPTS = _env_int("E2E_MAX_COVER_ATTEMPTS", 3)
E2E_MAX_PDF_ATTEMPTS = _env_int("E2E_MAX_PDF_ATTEMPTS", 3)
E2E_MAX_SAME_STAGE_VISITS = _env_int("E2E_MAX_SAME_STAGE_VISITS", 8)
E2E_STABLE_SESSION_ID = str(os.environ.get("E2E_STABLE_SESSION_ID", "")).strip()
E2E_REQUIRE_COVER_ARTIFACT = os.environ.get("E2E_REQUIRE_COVER_ARTIFACT", "0") == "1"
E2E_CV_ONLY = os.environ.get("E2E_CV_ONLY", "0") == "1"


def _enabled() -> bool:
    return os.environ.get("RUN_OPENAI_E2E") == "1" and bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _remaining_timeout(deadline_monotonic: float) -> int:
    remaining = int(deadline_monotonic - time.monotonic())
    if remaining <= 0:
        return 1
    return min(E2E_REQUEST_TIMEOUT_SEC, remaining)


def _call_tool(
    tool_name: str,
    params: dict | None = None,
    session_id: str | None = None,
    timeout_sec: int | None = None,
) -> dict:
    payload: dict = {"tool_name": tool_name, "params": params if isinstance(params, dict) else {}}
    if session_id:
        payload["session_id"] = session_id
    response = requests.post(
        f"{BASE_URL}/api/cv-tool-call-handler",
        json=payload,
        timeout=timeout_sec if isinstance(timeout_sec, int) and timeout_sec > 0 else E2E_REQUEST_TIMEOUT_SEC,
    )
    response.raise_for_status()
    body = response.json()
    assert isinstance(body, dict)
    return body


def _post_tool(params: dict, session_id: str | None = None, timeout_sec: int | None = None) -> dict:
    merged = dict(params or {})
    if session_id and not str(merged.get("session_id") or "").strip():
        merged["session_id"] = session_id
    return _call_tool("process_cv_orchestrated", params=merged, timeout_sec=timeout_sec)


def _available_action_ids(result: dict) -> list[str]:
    ui_action = result.get("ui_action") if isinstance(result.get("ui_action"), dict) else {}
    actions = ui_action.get("actions") if isinstance(ui_action.get("actions"), list) else []
    out: list[str] = []
    for action in actions:
        if isinstance(action, dict):
            aid = str(action.get("id") or "").strip()
            if aid:
                out.append(aid)
    return out


def _stage_is_job_input(stage: str) -> bool:
    return stage in {"job_posting", "job_posting_paste", "job_posting_invalid_input"}


@pytest.mark.skipif(not _enabled(), reason="RUN_OPENAI_E2E=1 and OPENAI_API_KEY required")
def test_e2e_lonza_dod_artifacts() -> None:
    started_at = time.monotonic()
    deadline = started_at + E2E_MAX_FLOW_SECONDS

    health = requests.get(f"{BASE_URL}/api/health", timeout=min(10, E2E_REQUEST_TIMEOUT_SEC))
    health.raise_for_status()

    assert SCENARIO_PATH.exists(), f"Missing scenario file: {SCENARIO_PATH}"

    scenario = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    metadata = scenario.get("metadata") if isinstance(scenario.get("metadata"), dict) else {}
    scenario_job_posting_url = str(metadata.get("job_posting_url") or "").strip()
    scenario_job_posting_text = str(metadata.get("job_posting_text") or "").strip()

    assert scenario_job_posting_url == "https://lonza.talent-community.com/app/project/61784"
    assert len(scenario_job_posting_text) > 400
    ok_job_text, reason = _looks_like_job_posting_text(scenario_job_posting_text)
    assert ok_job_text is True, f"Scenario job_posting_text rejected as invalid: {reason}"

    using_stable_session = bool(E2E_STABLE_SESSION_ID)
    result: dict
    session_id: str
    job_posting_url: str
    job_posting_text: str
    stage_progress: list[dict] = []

    def mark_stage(stage_name: str, ok: bool, detail: str = "") -> None:
        entry = {"stage": stage_name, "ok": bool(ok), "detail": str(detail or "")[:240]}
        stage_progress.append(entry)
        print(f"[STAGE {'PASS' if ok else 'FAIL'}] {stage_name} :: {entry['detail']}")

    if using_stable_session:
        session_id = E2E_STABLE_SESSION_ID
        snapshot = _call_tool(
            "get_cv_session",
            params={},
            session_id=session_id,
            timeout_sec=_remaining_timeout(deadline),
        )
        assert snapshot.get("success") is True, f"Stable session unavailable: {json.dumps(snapshot, ensure_ascii=False)}"
        snap_cv = snapshot.get("cv_data") if isinstance(snapshot.get("cv_data"), dict) else {}
        assert snap_cv, "Stable session has empty cv_data"
        snap_meta = snapshot.get("metadata") if isinstance(snapshot.get("metadata"), dict) else {}
        job_posting_url = str(snap_meta.get("job_posting_url") or "").strip() or scenario_job_posting_url
        job_posting_text = str(snap_meta.get("job_posting_text") or "").strip() or scenario_job_posting_text
        assert len(job_posting_text) > 400, "Stable session lacks usable job_posting_text"
        ok_job_text, reason = _looks_like_job_posting_text(job_posting_text)
        assert ok_job_text is True, f"Stable-session job text rejected: {reason}"
        mark_stage("session_input_quality", True, "stable session loaded and job posting validated")
        result = _post_tool(
            {
                "session_id": session_id,
                "message": "resume",
                "language": "en",
                "job_posting_url": job_posting_url,
                "job_posting_text": job_posting_text,
            },
            timeout_sec=_remaining_timeout(deadline),
        )
    else:
        assert SAMPLE_DOCX_PATH.exists(), f"Missing sample DOCX: {SAMPLE_DOCX_PATH}"
        docx_b64 = base64.b64encode(SAMPLE_DOCX_PATH.read_bytes()).decode("ascii")
        job_posting_url = scenario_job_posting_url
        job_posting_text = scenario_job_posting_text
        result = _post_tool(
            {
                "message": "start",
                "language": "en",
                "docx_base64": docx_b64,
                "job_posting_url": job_posting_url,
                "job_posting_text": job_posting_text,
            },
            timeout_sec=_remaining_timeout(deadline),
        )
        session_id = str(result.get("session_id") or "").strip()
        assert session_id, "No session_id returned"
        mark_stage("session_input_quality", True, "fresh session started with scenario job posting")

    cv_pdf_bytes: bytes | None = None
    cover_pdf_bytes: bytes | None = None
    cover_attempts = 0
    cover_status = "not_started"
    cover_timeout_count = 0
    cover_last_error = ""
    pdf_attempts = 0
    action_history: list[dict] = []

    visited: list[dict] = []
    last_stage = ""
    same_stage_visits = 0
    for step_idx in range(E2E_MAX_STEPS):
        now = time.monotonic()
        if now > deadline:
            pytest.fail(
                f"E2E flow exceeded deadline ({E2E_MAX_FLOW_SECONDS}s). "
                f"session_id={session_id} visited={json.dumps(visited, ensure_ascii=False)}"
            )

        stage = str(result.get("stage") or "").strip()
        if stage == last_stage:
            same_stage_visits += 1
        else:
            same_stage_visits = 1
            last_stage = stage
        if same_stage_visits > E2E_MAX_SAME_STAGE_VISITS:
            pytest.fail(
                f"No progress detected: stayed in stage '{stage}' for {same_stage_visits} consecutive visits. "
                f"session_id={session_id} visited={json.dumps(visited, ensure_ascii=False)}"
            )

        available = _available_action_ids(result)
        visited.append(
            {
                "step": step_idx + 1,
                "elapsed_sec": round(now - started_at, 2),
                "stage": stage,
                "actions": available[:8],
                "response": str(result.get("response") or "")[:200],
            }
        )

        if (
            cv_pdf_bytes is not None
            and not E2E_CV_ONLY
            and E2E_REQUIRE_COVER_ARTIFACT
            and stage not in {"review_final", "cover_letter_review"}
        ):
            cover_status = "blocked_after_cv"
            cover_last_error = f"Unexpected stage after CV generation: {stage or '(empty)'}"
            mark_stage("cover_letter_stage_entry", False, cover_last_error)
            break

        def send_action(action_id: str, message: str, payload: dict | None = None) -> dict:
            action_history.append({"stage": stage, "action_id": action_id})
            user_action = {"id": action_id}
            if isinstance(payload, dict) and payload:
                user_action["payload"] = payload
            try:
                return _post_tool(
                    {"session_id": session_id, "message": message, "user_action": user_action},
                    timeout_sec=_remaining_timeout(deadline),
                )
            except requests.exceptions.ReadTimeout:
                return {
                    "_timeout": True,
                    "stage": stage,
                    "response": f"timeout on action={action_id}",
                    "ui_action": {"actions": []},
                }

        if stage == "review_final" and cv_pdf_bytes is None and "REQUEST_GENERATE_PDF" in available:
            if pdf_attempts >= E2E_MAX_PDF_ATTEMPTS:
                pytest.fail(
                    f"CV PDF generation exceeded attempt cap ({E2E_MAX_PDF_ATTEMPTS}) without inline pdf_base64. "
                    f"session_id={session_id} visited={json.dumps(visited, ensure_ascii=False)}"
                )
            pdf_attempts += 1
            result = send_action("REQUEST_GENERATE_PDF", "generate pdf")
            pdf_b64 = str(result.get("pdf_base64") or "")
            if pdf_b64:
                cv_pdf_bytes = base64.b64decode(pdf_b64)
                assert len(cv_pdf_bytes) > 5000
                mark_stage("cv_pdf_generation", True, f"pdf_size={len(cv_pdf_bytes)}")
                if E2E_CV_ONLY:
                    cover_status = "skipped_cv_only"
                    break
            continue

        if stage == "review_final" and cv_pdf_bytes is not None and cover_pdf_bytes is None and "COVER_LETTER_PREVIEW" in available:
            result = send_action("COVER_LETTER_PREVIEW", "cover")
            if result.get("_timeout") is True:
                cover_timeout_count += 1
                cover_status = "timeout_preview"
                cover_last_error = "COVER_LETTER_PREVIEW timed out"
                mark_stage("cover_letter_preview", False, cover_last_error)
                break
            mark_stage("cover_letter_preview", True, "cover letter draft requested")
            continue

        if (
            stage == "review_final"
            and cv_pdf_bytes is not None
            and cover_pdf_bytes is None
            and E2E_REQUIRE_COVER_ARTIFACT
            and not E2E_CV_ONLY
            and "COVER_LETTER_PREVIEW" not in available
        ):
            cover_status = "preview_action_missing"
            cover_last_error = "COVER_LETTER_PREVIEW action not available after CV generation"
            mark_stage("cover_letter_preview", False, cover_last_error)
            break

        if stage == "cover_letter_review" and cover_pdf_bytes is None and "COVER_LETTER_GENERATE" in available:
            if cover_attempts >= E2E_MAX_COVER_ATTEMPTS:
                pytest.fail(
                    f"Cover letter generation exceeded attempt cap ({E2E_MAX_COVER_ATTEMPTS}). "
                    f"session_id={session_id} visited={json.dumps(visited, ensure_ascii=False)}"
                )
            cover_attempts += 1
            result = send_action("COVER_LETTER_GENERATE", "generate cover")
            if result.get("_timeout") is True:
                cover_timeout_count += 1
                cover_status = "timeout_generate"
                cover_last_error = "COVER_LETTER_GENERATE timed out"
                mark_stage("cover_letter_generate", False, cover_last_error)
                break
            pdf_b64 = str(result.get("pdf_base64") or "")
            if pdf_b64:
                cover_pdf_bytes = base64.b64decode(pdf_b64)
                assert len(cover_pdf_bytes) > 5000
                cover_status = "generated"
                mark_stage("cover_letter_generate", True, f"pdf_size={len(cover_pdf_bytes)}")
                break
            cover_status = "incomplete"
            cover_last_error = str(result.get("response") or "")[:300]
            mark_stage("cover_letter_generate", False, cover_last_error or "incomplete response")
            break

        if "LANGUAGE_SELECT_EN" in available:
            result = send_action("LANGUAGE_SELECT_EN", "English")
            continue

        if "CONFIRM_IMPORT_PREFILL_YES" in available:
            if using_stable_session:
                cover_status = "blocked_pending_prefill_confirmation"
                cover_last_error = (
                    "Stable session requires prefill confirmation; canonical session data is not finalized. "
                    "Do not auto-import prefill in stable-session validation."
                )
                mark_stage("session_input_quality", False, cover_last_error)
                break
            result = send_action("CONFIRM_IMPORT_PREFILL_YES", "import")
            continue

        if "CONTACT_CONFIRM" in available:
            result = send_action("CONTACT_CONFIRM", "confirm")
            continue

        if "EDUCATION_CONFIRM" in available:
            result = send_action("EDUCATION_CONFIRM", "confirm")
            continue

        if "JOB_OFFER_CONTINUE" in available and _stage_is_job_input(stage):
            result = send_action("JOB_OFFER_CONTINUE", "continue")
            continue

        if "JOB_OFFER_ANALYZE" in available and _stage_is_job_input(stage):
            result = send_action("JOB_OFFER_ANALYZE", "analyze", {"job_offer_text": job_posting_text})
            continue

        if "JOB_OFFER_INVALID_CONTINUE_NO_SUMMARY" in available:
            result = send_action("JOB_OFFER_INVALID_CONTINUE_NO_SUMMARY", "continue")
            continue

        if "WORK_TAILOR_SKIP" in available:
            result = send_action("WORK_TAILOR_SKIP", "continue")
            continue

        if "WORK_NOTES_CANCEL" in available:
            result = send_action("WORK_NOTES_CANCEL", "cancel")
            continue

        if "WORK_TAILOR_ACCEPT" in available:
            result = send_action("WORK_TAILOR_ACCEPT", "accept")
            continue

        if "FURTHER_TAILOR_SKIP" in available:
            result = send_action("FURTHER_TAILOR_SKIP", "continue")
            continue

        if "FURTHER_NOTES_CANCEL" in available:
            result = send_action("FURTHER_NOTES_CANCEL", "cancel")
            continue

        if "FURTHER_TAILOR_ACCEPT" in available:
            result = send_action("FURTHER_TAILOR_ACCEPT", "accept")
            continue

        if "SKILLS_TAILOR_SKIP" in available:
            result = send_action("SKILLS_TAILOR_SKIP", "continue")
            continue

        if "SKILLS_NOTES_CANCEL" in available:
            result = send_action("SKILLS_NOTES_CANCEL", "cancel")
            continue

        if "SKILLS_TAILOR_ACCEPT" in available:
            result = send_action("SKILLS_TAILOR_ACCEPT", "accept")
            continue

        break

    assert cv_pdf_bytes is not None, f"CV PDF artifact not generated. Visited={json.dumps(visited, ensure_ascii=False)}"
    if E2E_CV_ONLY:
        assert cover_attempts == 0, "CV-only mode must not run cover letter generation"
    if E2E_REQUIRE_COVER_ARTIFACT:
        assert cover_pdf_bytes is not None, (
            f"Cover letter PDF artifact not generated after {cover_attempts} attempts. "
            f"Status={cover_status}; error={cover_last_error}; Visited={json.dumps(visited, ensure_ascii=False)}"
        )
    unsafe_job_actions = [
        a for a in action_history
        if a.get("action_id") == "JOB_OFFER_ANALYZE" and not _stage_is_job_input(str(a.get("stage") or ""))
    ]
    assert not unsafe_job_actions, f"JOB_OFFER_ANALYZE dispatched outside job stage: {json.dumps(unsafe_job_actions, ensure_ascii=False)}"

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cv_path = ARTIFACT_DIR / "lonza_cv_test_e2e.pdf"
    cl_path = ARTIFACT_DIR / "lonza_cover_letter_test_e2e.pdf"
    manifest_path = ARTIFACT_DIR / "lonza_dod_manifest.json"

    cv_path.write_bytes(cv_pdf_bytes)
    if cover_pdf_bytes is not None:
        cl_path.write_bytes(cover_pdf_bytes)
    manifest_path.write_text(
        json.dumps(
            {
                "session_id": session_id,
                "stable_session_resume": using_stable_session,
                "job_posting_url": job_posting_url,
                "cv_artifact": str(cv_path).replace("\\", "/"),
                "cover_letter_artifact": str(cl_path).replace("\\", "/") if cover_pdf_bytes is not None else "",
                "cv_size": len(cv_pdf_bytes),
                "cover_letter_size": len(cover_pdf_bytes) if cover_pdf_bytes is not None else 0,
                "cover_attempts": cover_attempts,
                "cover_status": cover_status,
                "cover_timeout_count": cover_timeout_count,
                "cover_last_error": cover_last_error,
                "require_cover_artifact": E2E_REQUIRE_COVER_ARTIFACT,
                "cv_only_mode": E2E_CV_ONLY,
                "stage_progress": stage_progress,
                "max_steps": E2E_MAX_STEPS,
                "max_flow_seconds": E2E_MAX_FLOW_SECONDS,
                "elapsed_seconds": round(time.monotonic() - started_at, 2),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    assert cv_path.exists()
    if E2E_REQUIRE_COVER_ARTIFACT:
        assert cl_path.exists()
    assert manifest_path.exists()