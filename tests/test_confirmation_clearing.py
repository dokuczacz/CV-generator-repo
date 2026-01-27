"""
Test confirmation clearing behavior (fix for infinite loop).

Verifies that pending_confirmation is cleared when FSM enters CONFIRM stage,
preventing the infinite REVIEW→CONFIRM→REVIEW loop.
"""

import os
import pytest


ENDPOINT = os.environ.get("CV_ENDPOINT", "http://localhost:7071/api")


def test_confirmation_clears_on_confirm_entry():
    """
    Test that pending_confirmation is cleared when FSM enters CONFIRM stage.
    
    Steps:
    1. Upload DOCX → creates docx_prefill_unconfirmed + pending_confirmation
    2. Send 3 messages in REVIEW → FSM auto-advances to CONFIRM
    3. Verify pending_confirmation is cleared
    4. Send "generate pdf" → should reach EXECUTE stage (no loop)
    """
    import requests
    
    # 1. Upload DOCX
    with open("samples/Lebenslauf_Mariusz_Horodecki_CH.docx", "rb") as f:
        r = requests.post(
            f"{ENDPOINT}/cleanup",
            timeout=10,
        )
        print(f"[CLEANUP] {r.status_code}")
        
        r = requests.post(
            f"{ENDPOINT}/ingest-cv",
            files={"file": ("test.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            timeout=60,
        )
        assert r.status_code == 200, f"Ingest failed: {r.status_code} {r.text}"
        data = r.json()
        session_id = data["session_id"]
        print(f"[INGEST] session={session_id}")
    
    # Check pending_confirmation is set
    r = requests.get(f"{ENDPOINT}/get-session?session_id={session_id}", timeout=10)
    assert r.status_code == 200
    sess = r.json()
    meta = sess.get("metadata", {})
    pc = meta.get("pending_confirmation")
    assert pc is not None, "pending_confirmation should be set after ingest"
    assert pc.get("kind") == "import_prefill"
    print(f"[CHECK] pending_confirmation set: {pc}")
    
    # 2. Send 3 messages to trigger auto-advance REVIEW→CONFIRM
    for i in range(3):
        r = requests.post(
            f"{ENDPOINT}/process-cv",
            json={
                "session_id": session_id,
                "user_message": f"tell me about yourself (turn {i+1})",
                "max_model_calls": 1,
            },
            timeout=120,
        )
        assert r.status_code == 200, f"Turn {i+1} failed: {r.status_code} {r.text}"
        data = r.json()
        print(f"[TURN {i+1}] stage={data.get('metadata', {}).get('stage')}")
    
    # 3. Check FSM reached CONFIRM and pending_confirmation was cleared
    r = requests.get(f"{ENDPOINT}/get-session?session_id={session_id}", timeout=10)
    assert r.status_code == 200
    sess = r.json()
    meta = sess.get("metadata", {})
    stage = meta.get("stage")
    pc_after = meta.get("pending_confirmation")
    
    print(f"[VERIFY] stage={stage}, pending_confirmation={pc_after}")
    assert stage == "CONFIRM", f"Expected CONFIRM stage, got {stage}"
    assert pc_after is None, f"pending_confirmation should be cleared, got {pc_after}"
    
    # 4. Send "generate pdf" → should reach EXECUTE (no loop back to REVIEW)
    r = requests.post(
        f"{ENDPOINT}/process-cv",
        json={
            "session_id": session_id,
            "user_message": "generate pdf",
            "max_model_calls": 1,
        },
        timeout=120,
    )
    assert r.status_code == 200, f"Generate request failed: {r.status_code} {r.text}"
    data = r.json()
    final_stage = data.get("metadata", {}).get("stage")
    
    print(f"[FINAL] stage={final_stage}")
    # Should reach EXECUTE or DONE (not stuck in REVIEW)
    assert final_stage in ("EXECUTE", "DONE"), f"Expected EXECUTE/DONE, got {final_stage} (loop detected)"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
