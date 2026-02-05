#!/usr/bin/env python3
"""
Test: CV generation in German (DE) language — verify output language is actually German
Usage:
  cd "c:/AI memory/CV-generator-repo"
  python tests/test_german_cv_generation.py
"""

import json
import sys
import time
from pathlib import Path

# Add repo root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests
import base64

BASE_URL = "http://localhost:7071/api"

def test_german_cv_generation_e2e():
    """
    End-to-end test: German CV generation with language verification.
    Tests that work_experience stage produces German output, not English.
    """
    
    print("\n" + "="*80)
    print("TEST: German CV Generation Language Output Verification")
    print("="*80)
    
    # Step 1: Check if sample DOCX exists
    sample_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
    if not sample_path.exists():
        print(f"⚠ Sample DOCX not found at {sample_path}")
        return False
    
    print("\n[1] Loading sample DOCX...")
    with open(sample_path, "rb") as f:
        docx_bytes = f.read()
    
    import base64
    docx_b64 = base64.b64encode(docx_bytes).decode('ascii')
    print(f"✓ DOCX loaded ({len(docx_bytes)} bytes)")
    
    # Step 2: Create session with German language using extract_and_store_cv
    print("\n[2] Creating session with German language...")
    
    payload = {
        "tool_name": "extract_and_store_cv",
        "params": {
            "docx_base64": docx_b64,
            "language": "de",
            "extract_photo_flag": True
        }
    }
    
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=60)
    if resp.status_code != 200:
        print(f"❌ Failed to create session: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    
    result = resp.json()
    session_id = result.get("session_id")
    if not session_id:
        print(f"❌ No session_id in response: {result}")
        return False
    
    print(f"✓ Session created: {session_id}")
    
    cv_data = result.get("cv_data", {})
    meta = result.get("metadata", {})
    print(f"  Target language: {meta.get('target_language', 'unknown')}")
    print(f"  Full name: {cv_data.get('full_name', 'unknown')}")
    print(f"  Work roles: {len(cv_data.get('work_experience', []))}")
    
    # Step 3: Confirm contact
    print("\n[3] Confirming contact information...")
    
    payload = {
        "tool_name": "user_action",
        "session_id": session_id,
        "params": {
            "action_id": "CONTACT_CONFIRM"
        }
    }
    
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Contact confirm failed: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    print("✓ Contact confirmed")
    
    # Step 4: Confirm education
    print("\n[4] Confirming education...")
    
    payload = {
        "tool_name": "user_action",
        "session_id": session_id,
        "params": {
            "action_id": "EDUCATION_CONFIRM"
        }
    }
    
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Education confirm failed: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    print("✓ Education confirmed")
    
    # Step 5: Skip job posting
    print("\n[5] Skipping job posting...")
    
    payload = {
        "tool_name": "user_action",
        "session_id": session_id,
        "params": {
            "action_id": "JOB_POSTING_SKIP"
        }
    }
    
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=10)
    if resp.status_code != 200:
        print(f"❌ Job posting skip failed: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    print("✓ Job posting skipped")
    
    # Step 6: Tailor work experience in German (CRITICAL TEST)
    print("\n[6] Running work experience tailoring in German...")
    print("    >>> This call MUST produce German output, not English! <<<")
    
    payload = {
        "tool_name": "user_action",
        "session_id": session_id,
        "params": {
            "action_id": "WORK_TAILOR_RUN"
        }
    }
    
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json=payload, timeout=120)
    if resp.status_code != 200:
        print(f"❌ Work tailoring failed: {resp.status_code}")
        print(f"Response: {resp.text[:500]}")
        return False
    
    
    result = resp.json()
    meta = result.get("metadata", {})
    cv_out = result.get("cv_data", {})
    
    
    print(f"✓ Work experience tailored")
    print(f"  Target language in metadata: {meta.get('target_language', 'unknown')}")
    print(f"  Bulk translated to: {meta.get('bulk_translated_to', 'not-set')}")
    
    # Step 7: Check language of work_experience output
    print("\n[7] Analyzing work experience output language...")
    
    work_exp = cv_out.get("work_experience", [])
    print(f"  Work roles in output: {len(work_exp)}")
    
    # Collect all bullets to analyze language
    all_bullets = []
    for role_idx, role in enumerate(work_exp):
        if not isinstance(role, dict):
            print(f"  [Warning] Role {role_idx+1} is not a dict: {type(role)}")
            continue
        bullets = role.get("bullets", [])
        if not isinstance(bullets, list):
            bullets = []
        for bullet_idx, bullet in enumerate(bullets):
            bullet_str = str(bullet)
            all_bullets.append(bullet_str)
            print(f"    Role {role_idx+1}, Bullet {bullet_idx+1}: {bullet_str[:120]}...")
    
    if not all_bullets:
        print("  ❌ No bullets found in work_experience output!")
        return False
    
    # Step 8: Language detection heuristic
    print("\n[8] Detecting language of output...")
    
    german_indicators = 0
    english_indicators = 0
    
    # German keywords/patterns
    german_words = [
        "und", "den", "der", "die", "das", "ein", "eine", "ist", "zu", "für",
        "mit", "von", "bei", "auf", "um", "am", "im", "vom", "zum", "zur",
        "entwickelt", "implementiert", "erstellt", "verbessert", "optimiert",
        "durchgeführt", "unterstützt", "gelöst", "reduziert", "erhöht",
        "Prozess", "System", "Überwachung", "Verbesserung", "Benutzern",
        "verbessern", "durchzuführen", "unterstützung"
    ]
    
    # English keywords/patterns
    english_words = [
        "and", "the", "a", "to", "of", "in", "for", "with", "that", "on",
        "developed", "implemented", "created", "improved", "optimized",
        "designed", "deployed", "built", "support", "led", "reduced",
        "increased", "resolved", "System", "Process", "Users", "Features",
    ]
    
    full_text = " ".join(all_bullets).lower()
    
    for word in german_words:
        german_indicators += full_text.count(word.lower())
    
    for word in english_words:
        english_indicators += full_text.count(word.lower())
    
    print(f"  German keyword hits: {german_indicators}")
    print(f"  English keyword hits: {english_indicators}")
    
    # Step 9: Final verdict
    print("\n[9] LANGUAGE VERIFICATION RESULT:")
    print("="*80)
    
    if german_indicators > english_indicators:
        print("✅ SUCCESS: Output appears to be in GERMAN")
        print(f"   German: {german_indicators} vs English: {english_indicators}")
        return True
    else:
        print("❌ FAILURE: Output appears to be in ENGLISH (not German!)")
        print(f"   German: {german_indicators} vs English: {english_indicators}")
        print("\nSample bullets from output:")
        for i, bullet in enumerate(all_bullets[:3]):
            print(f"  {i+1}. {bullet}")
        return False


if __name__ == "__main__":
    try:
        success = test_german_cv_generation_e2e()
        print("\n" + "="*80)
        if success:
            print("✅ TEST PASSED")
        else:
            print("❌ TEST FAILED")
        print("="*80 + "\n")
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ TEST CRASHED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(2)
