#!/usr/bin/env python3
"""Opt-in local E2E smoke for German language output in work tailoring stage."""

import base64
import os
from pathlib import Path

import pytest
import requests

BASE_URL = "http://localhost:7071/api"


@pytest.mark.skipif(
    os.environ.get("RUN_LOCAL_DE_E2E") != "1",
    reason="Set RUN_LOCAL_DE_E2E=1 to run local German language smoke test",
)
def test_german_lang_output_local_host():
    sample_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
    assert sample_path.exists(), f"No DOCX at {sample_path}"

    with open(sample_path, "rb") as file_handle:
        docx_b64 = base64.b64encode(file_handle.read()).decode("ascii")

    resp = requests.post(
        f"{BASE_URL}/cv-tool-call-handler",
        json={
            "tool_name": "process_cv_orchestrated",
            "params": {
                "docx_base64": docx_b64,
                "language": "de",
                "message": "start",
            },
        },
        timeout=60,
    )
    assert resp.status_code == 200
    data = resp.json()
    session_id = data.get("session_id")
    assert session_id, "Missing session_id"

    if data.get("stage") == "language_selection":
        resp = requests.post(
            f"{BASE_URL}/cv-tool-call-handler",
            json={
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "session_id": session_id,
                    "message": "German",
                    "user_action": {"id": "LANGUAGE_SELECT_DE"},
                },
            },
            timeout=60,
        )
        assert resp.status_code == 200

    for action_id in ["CONTACT_CONFIRM", "CONFIRM_IMPORT_PREFILL_YES", "CONTACT_CONFIRM", "EDUCATION_CONFIRM", "JOB_POSTING_SKIP"]:
        resp = requests.post(
            f"{BASE_URL}/cv-tool-call-handler",
            json={
                "tool_name": "process_cv_orchestrated",
                "params": {
                    "session_id": session_id,
                    "message": "continue",
                    "user_action": {"id": action_id},
                },
            },
            timeout=120,
        )
        assert resp.status_code == 200

    resp = requests.post(
        f"{BASE_URL}/cv-tool-call-handler",
        json={
            "tool_name": "process_cv_orchestrated",
            "params": {
                "session_id": session_id,
                "message": "tailor",
                "user_action": {"id": "WORK_TAILOR_RUN"},
            },
        },
        timeout=180,
    )
    assert resp.status_code == 200
    data = resp.json()

    work_exp = data.get("cv_data", {}).get("work_experience", [])
    bullets = [
        str(bullet)
        for role in work_exp
        if isinstance(role, dict)
        for bullet in role.get("bullets", [])
    ]
    assert bullets, "No work-experience bullets found in response"

    full_text = " ".join(bullets).lower()
    german_count = sum(full_text.count(word) for word in [" und ", " der ", " die ", " das ", "prozess", "system"])
    english_count = sum(full_text.count(word) for word in [" and ", " the ", "process", "system"])

    assert german_count > english_count and german_count > 0, "Expected German-dominant output"
