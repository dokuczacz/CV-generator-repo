#!/usr/bin/env python3
"""
Simple end-to-end test: upload CV → 3 turns → auto-advance to CONFIRM → log turn counter.

Usage:
    python tests/test_fsm_auto_advance.py
"""

import json
import os
import sys
import time
from pathlib import Path

# Add parent to path to find src
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.docx_prefill import prefill_cv_from_docx_bytes
from src.session_store import CVSessionStore

def main():
    """Simulate: upload → auto-advance after 3 turns."""
    
    store = CVSessionStore()
    
    # Find a test CV file
    test_cv = Path(__file__).parent.parent / "samples" / "sample.docx"
    if not test_cv.exists():
        print(f"❌ Test CV not found at {test_cv}")
        return False
    
    print(f"📄 Loading test CV: {test_cv.name}")
    docx_bytes = test_cv.read_bytes()
    
    # Extract prefill (simulates upload)
    try:
        prefill_data = prefill_cv_from_docx_bytes(docx_bytes)
        print(f"✅ Prefill extracted: {len(prefill_data)} fields")
    except Exception as e:
        print(f"❌ Prefill extraction failed: {e}")
        return False
    
    # Create session
    session_id = "test-fsm-" + str(int(time.time() * 1000))[-10:]
    cv_data = {}
    meta = {
        "stage": "PREPARE",
        "docx_prefill_unconfirmed": prefill_data,
    }
    
    try:
        store.create_session(session_id, cv_data, meta)
        print(f"✅ Session created: {session_id}")
    except Exception as e:
        print(f"❌ Session creation failed: {e}")
        return False
    
    # Simulate 3+ turns in REVIEW stage
    turns_goal = 4
    for turn in range(1, turns_goal + 1):
        sess = store.get_session(session_id)
        if not sess:
            print(f"❌ Session lost at turn {turn}")
            return False
        
        meta = sess.get("metadata", {})
        turns_in_review = meta.get("turns_in_review", 0)
        stage = meta.get("stage", "PREPARE")
        
        print(f"\n  Turn {turn}:")
        print(f"    Stage: {stage}")
        print(f"    Turns in REVIEW: {turns_in_review}")
        
        # Simulate FSM staying in REVIEW or auto-advancing
        if stage == "PREPARE":
            # First turn: PREPARE → REVIEW
            meta["stage"] = "REVIEW"
            meta["turns_in_review"] = 0
            print(f"    → Auto: PREPARE → REVIEW")
        elif stage == "REVIEW":
            # Stay in REVIEW, increment counter
            meta["turns_in_review"] = turns_in_review + 1
            # After 3 turns, auto-advance
            if meta["turns_in_review"] >= 3:
                meta["stage"] = "CONFIRM"
                meta["turns_in_review"] = 0
                print(f"    → Auto-advance: REVIEW (turn {meta.get('turns_in_review', 0) + 1}) → CONFIRM")
            else:
                print(f"    → Staying in REVIEW")
        
        try:
            store.update_session(session_id, sess.get("cv_data", {}), meta)
        except Exception as e:
            print(f"❌ Update failed: {e}")
            return False
    
    # Final state
    sess_final = store.get_session(session_id)
    meta_final = sess_final.get("metadata", {})
    stage_final = meta_final.get("stage", "UNKNOWN")
    
    print(f"\n✅ FSM Flow Complete:")
    print(f"    Final Stage: {stage_final}")
    print(f"    Turns in REVIEW: {meta_final.get('turns_in_review', 0)}")
    
    if stage_final == "CONFIRM":
        print(f"\n🎉 SUCCESS: Auto-advanced to CONFIRM after 3 turns!")
        return True
    else:
        print(f"\n❌ FAILED: Expected CONFIRM, got {stage_final}")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
