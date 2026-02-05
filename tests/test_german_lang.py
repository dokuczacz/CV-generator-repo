#!/usr/bin/env python3
"""
Test: Full CV generation flow in German 
"""

import json
import sys
from pathlib import Path
import requests
import base64

BASE_URL = "http://localhost:7071/api"

sample_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
if not sample_path.exists():
    print(f"ERROR: No DOCX at {sample_path}")
    sys.exit(1)

print("\n" + "="*80)
print("TEST: GERMAN CV GENERATION IN DE LANGUAGE")
print("="*80)

with open(sample_path, "rb") as f:
    docx_b64 = base64.b64encode(f.read()).decode('ascii')

# Step 1: Start DOCX upload with language=de in params
print("\n1. Starting with DOCX (language=de)...")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "docx_base64": docx_b64,
        "language": "de",
        "message": "start"
    }
}, timeout=60)

if resp.status_code != 200:
    print(f"ERROR: {resp.status_code}")
    print(resp.text[:500])
    sys.exit(1)

r = resp.json()
session_id = r.get("session_id")
stage = r.get("stage")
target_lang = r.get("metadata", {}).get("target_language")

print(f"[OK] Session: {session_id}")
print(f"  Stage: {stage}")
print(f"  Target language: {target_lang}")

# Step 1.5: If language_selection stage, select DE
if stage == 'language_selection':
    print("\n1.5. Selecting German language...")
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
        "tool_name": "process_cv_orchestrated",
        "params": {
            "session_id": session_id,
            "message": "German",
            "user_action": {"id": "LANGUAGE_SELECT_DE"}
        }
    }, timeout=60)
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code}")
        print(resp.text[:500])
        sys.exit(1)
    r = resp.json()
    stage = r.get("stage")
    target_lang = r.get("metadata", {}).get("target_language")
    print(f"[OK] Stage: {stage}")
    print(f"  Target language: {target_lang}")

# Step 2-4: Navigate through contact, education, job_posting
for step_info in [
    (2, "CONTACT_CONFIRM", "contact"),
    (3, "EDUCATION_CONFIRM", "education"),
    (4, "JOB_POSTING_SKIP", "job_posting"),
]:
    step_num, action_id, stage_name = step_info
    print(f"\n{step_num}. {stage_name.replace('_', ' ').title()}...")
    
    resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
        "tool_name": "process_cv_orchestrated",
        "params": {
            "session_id": session_id,
            "message": "confirm",
            "user_action": {"id": action_id}
        }
    }, timeout=60)
    
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code}")
        print(resp.text[:500])
        # Try to continue anyway
        continue
    
    r = resp.json()
    stage = r.get("stage")
    target_lang = r.get("metadata", {}).get("target_language")
    
    print(f"[OK] Stage: {stage}")
    print(f"  Target language: {target_lang}")
    
    # Handle import gate if needed
    if stage == 'import_gate_pending':
        print(f"\n{step_num}.5. Importing DOCX data...")
        resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
            "tool_name": "process_cv_orchestrated",
            "params": {
                "session_id": session_id,
                "message": "yes",
                "user_action": {"id": "CONFIRM_IMPORT_PREFILL_YES"}
            }
        }, timeout=120)
        if resp.status_code == 200:
            r = resp.json()
            stage = r.get("stage")
            target_lang = r.get("metadata", {}).get("target_language")  
            print(f"[OK] Stage: {stage}")
            print(f"  Target language: {target_lang}")

# Step 5: RUN WORK EXPERIENCE TAILORING IN GERMAN
print("\n5. RUNNING WORK EXPERIENCE TAILORING IN GERMAN...")
print("   >>> Checking if output is DEUTSCH or ENGLISH <<<")

resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "tailor",
        "user_action": {"id": "WORK_TAILOR_RUN"}
    }
}, timeout=180)

print(f"DEBUG: Response status={resp.status_code}")
print(f"DEBUG: Response body={resp.text[:1000]}")

if resp.status_code != 200:
    print(f"ERROR: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

r = resp.json()
stage = r.get("stage")
target_lang = r.get("metadata", {}).get("target_language")
bulk_xlated_to = r.get("metadata", {}).get("bulk_translated_to")

print(f"[OK] Stage: {stage}")
print(f"  Target language: {target_lang}")
print(f"  Bulk translated to: {bulk_xlated_to}")

# DEBUG: Print full cv_data.work_experience structure
print(f"\nDEBUG: cv_data keys={list(r.get('cv_data', {}).keys())}")
print(f"DEBUG: work_experience type={type(r.get('cv_data', {}).get('work_experience'))}")
work_exp_data = r.get('cv_data', {}).get('work_experience')
if work_exp_data:
    print(f"DEBUG: work_experience length={len(work_exp_data)}")
    print(f"DEBUG: work_experience[0] keys={list(work_exp_data[0].keys()) if work_exp_data and isinstance(work_exp_data[0], dict) else 'N/A'}")
    if work_exp_data and isinstance(work_exp_data[0], dict):
        bullets = work_exp_data[0].get('bullets', [])
        print(f"DEBUG: work_experience[0].bullets={bullets[:100] if bullets else 'EMPTY'}")
else:
    print(f"DEBUG: work_experience is {work_exp_data}")

# Check the work experience bullets
work_exp = r.get('cv_data', {}).get('work_experience', [])
all_bullets = []

if isinstance(work_exp, list):
    for i, role in enumerate(work_exp):
        if isinstance(role, dict):
            bullets = role.get('bullets', [])
            for j, bullet in enumerate(bullets):
                bullet_str = str(bullet)
                all_bullets.append(bullet_str)
                if j < 2:  # Show first 2 bullets per role
                    print(f"    Role {i+1} Bullet {j+1}: {bullet_str[:110]}")
else:
    print(f"  work_experience is not a list: {type(work_exp)}")

if not all_bullets:
    print("  WARNING: No bullets found!")

# Language detection
print("\n6. LANGUAGE DETECTION:")
german_count = 0
english_count = 0
full_text = " ".join(all_bullets).lower()

# German words
for word in ["und", "der", "die", "das", "entwickelt", "implementiert", "verbessert", "durchgefuhrt", "Prozess", "System"]:
    german_count += full_text.count(word.lower())

# English words  
for word in ["and", "the", "developed", "implemented", "created", "improved", "System", "Process"]:
    english_count += full_text.count(word.lower())

print(f"  German keywords: {german_count}")
print(f"  English keywords: {english_count}")

print("\n" + "="*80)
if german_count > english_count and german_count > 0:
    print("[PASS] Output is in GERMAN")
    sys.exit(0)
else:
    print("[FAIL] Output is in ENGLISH (not German!)")
    print("\nSample output:")
    for i, bullet in enumerate(all_bullets[:3]):
        print(f"  {i+1}. {bullet}")
    sys.exit(1)
