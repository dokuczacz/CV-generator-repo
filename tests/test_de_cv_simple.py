#!/usr/bin/env python3
"""
Simple test: Full CV generation flow in German with language diagnostic
"""

import json
import sys
from pathlib import Path
import requests
import base64

BASE_URL = "http://localhost:7071/api"

sample_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
assert sample_path.exists(), f"No DOCX at {sample_path}"

print("\n" + "="*80)
print("GERMAN CV GENERATION TEST")
print("="*80)

with open(sample_path, "rb") as f:
    docx_b64 = base64.b64encode(f.read()).decode('ascii')

# Step 1: Start DOCX upload with language=de in params
print("\n1. Starting with DOCX and language=de...")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "docx_base64": docx_b64,
        "language": "de",
        "message": "start"
    }
}, timeout=60)

assert resp.status_code == 200, f"Initial call failed: {resp.status_code}\n{resp.text[:500]}"
r = resp.json()
session_id = r.get("session_id")
print(f"✓ Session: {session_id}")
print(f"  Stage: {r.get('stage', 'unknown')}")
print(f"  Lang in metadata: {r.get('metadata', {}).get('target_language', 'not-set')}")

# Step 1.5: If language_selection stage, select DE
stage = r.get('stage')
if stage == 'language_selection':
    print("\n1.5. Selecting German (Deutsch)...")
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
        "tool_name": "process_cv_orchestrated",
        "params": {
            "session_id": session_id,
            "message": "German",
            "user_action": {"id": "LANGUAGE_SELECT_DE"}
        }
    }, timeout=60)
    assert resp.status_code == 200
    r = resp.json()
    print(f"✓ Stage: {r.get('stage')}")
    print(f"  Lang in metadata: {r.get('metadata', {}).get('target_language', 'not-set')}")

# Step 2: Confirm contact
print("\n2. Confirming contact...")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "confirm",
        "user_action": {"id": "CONTACT_CONFIRM"}
    }
}, timeout=30)
assert resp.status_code == 200
r = resp.json()
stage = r.get('stage')
print(f"✓ Stage: {stage}")
print(f"  Lang in metadata: {r.get('metadata', {}).get('target_language', 'not-set')}")

if stage == 'import_gate_pending':
    print("\n2.5. Confirming DOCX import...")
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
        "tool_name": "process_cv_orchestrated",
        "params": {
            "session_id": session_id,
            "message": "yes",
            "user_action": {"id": "CONFIRM_IMPORT_PREFILL_YES"}
        }
    }, timeout=120)
    assert resp.status_code == 200
    r = resp.json()
    stage = r.get('stage')
    print(f"✓ Stage: {stage}")
    print(f"  Lang in metadata: {r.get('metadata', {}).get('target_language', 'not-set')}")

# Re-confirm contact if still on contact stage
if stage == 'contact':
    print("\n2.75. Re-confirming contact after import...")
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
        "tool_name": "process_cv_orchestrated",
        "params": {
            "session_id": session_id,
            "message": "confirm",
            "user_action": {"id": "CONTACT_CONFIRM"}
        }
    }, timeout=30)
    assert resp.status_code == 200
    r = resp.json()
    stage = r.get('stage')
    print(f"✓ Stage: {stage}")

# Step 3: Confirm education
print("\n3. Confirming education...")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "confirm",
        "user_action": {"id": "EDUCATION_CONFIRM"}
    }
}, timeout=30)
assert resp.status_code == 200
r = resp.json()
print(f"✓ Stage: {r.get('stage')}")

# Step 4: Skip job posting
print("\n4. Skipping job posting...")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "skip",
        "user_action": {"id": "JOB_POSTING_SKIP"}
    }
}, timeout=30)
assert resp.status_code == 200
r = resp.json()
print(f"✓ Stage: {r.get('stage')}")

# Step 5: RUN WORK EXPERIENCE TAILORING IN GERMAN
print("\n5. RUNNING WORK EXPERIENCE TAILORING IN GERMAN...")
print("   >>> This must produce DEUTSCH output, not English! <<<")
print("   Checking backend logs for: PROMPT_LANG_SUBSTITUTION, WORK_TAILOR_CONTEXT, target_language=de")
print()

resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "tailor",
        "user_action": {"id": "WORK_TAILOR_RUN"}
    }
}, timeout=120)

if resp.status_code != 200:
    print(f"❌ Failed: {resp.status_code}")
    print(resp.text[:500])
    sys.exit(1)

r = resp.json()
print(f"✓ Stage: {r.get('stage')}")
print(f"  Metadata lang: {r.get('metadata', {}).get('target_language')}")
print(f"  Bulk xlated to: {r.get('metadata', {}).get('bulk_translated_to')}")

# Check the work experience bullets
work_exp = r.get('cv_data', {}).get('work_experience', [])
all_bullets = []
for i, role in enumerate(work_exp):
    if isinstance(role, dict):
        for j, bullet in enumerate(role.get('bullets', [])):
            all_bullets.append(str(bullet))
            print(f"  Role {i+1} Bullet {j+1}: {str(bullet)[:110]}")

# Language detection
print("\n6. LANGUAGE DETECTION:")
german_count = 0
english_count = 0
full_text = " ".join(all_bullets).lower()

# German words
for word in ["und", "der", "die", "das", "entwickelt", "implementiert", "verbessert", "durchgeführt", "Prozess", "System"]:
    german_count += full_text.count(word.lower())

# English words
for word in ["and", "the", "developed", "implemented", "created", "improved", "System", "Process"]:
    english_count += full_text.count(word.lower())

print(f"  German keywords: {german_count}")  
print(f"  English keywords: {english_count}")

print("\n" + "="*80)
if german_count > english_count:
    print("✅ SUCCESS - Output is in GERMAN")
    sys.exit(0)
else:
    print("❌ FAILURE - Output is in ENGLISH (not German!)")
    print("\nSample bullets:")
    for bullet in all_bullets[:3]:
        print(f"  → {bullet}")
    sys.exit(1)
