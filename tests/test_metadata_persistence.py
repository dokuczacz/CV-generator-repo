#!/usr/bin/env python3
"""
Test: Metadata persistence across API calls (especially target_language field)
"""

import json
import sys
import base64
import requests
from pathlib import Path

BASE_URL = "http://localhost:7071/api"

sample_path = Path("samples/Lebenslauf_Mariusz_Horodecki_CH.docx")
if not sample_path.exists():
    print(f"ERROR: No DOCX at {sample_path}")
    sys.exit(1)

print("\n" + "="*80)
print("TEST: Metadata Persistence (target_language field)")
print("="*80)

with open(sample_path, "rb") as f:
    docx_b64 = base64.b64encode(f.read()).decode('ascii')

# Step 1: Start DOCX upload with language=de
print("\nStep 1: Upload DOCX with language=de")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "docx_base64": docx_b64,
        "language": "de",
        "message": "start"
    }
}, timeout=30)

if resp.status_code != 200:
    print(f"ERROR: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

r = resp.json()
session_id = r.get("session_id")
stage = r.get("stage")
metadata = r.get("metadata", {})

print(f"[✓] Session created: {session_id}")
print(f"    Stage: {stage}")
print(f"    Metadata keys: {list(metadata.keys())}")
print(f"    target_language in metadata: {metadata.get('target_language')}")

if stage != 'language_selection':
    print(f"ERROR: Expected language_selection stage, got {stage}")
    sys.exit(1)

# Step 2: Select German language
print("\nStep 2: Select LANGUAGE_SELECT_DE")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "German",
        "user_action": {"id": "LANGUAGE_SELECT_DE"}
    }
}, timeout=30)

if resp.status_code != 200:
    print(f"ERROR: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

r = resp.json()
stage = r.get("stage")
metadata = r.get("metadata", {})
target_lang = metadata.get("target_language")

print(f"[✓] Language selected")
print(f"    Stage: {stage}")
print(f"    target_language: {target_lang}")

if target_lang != "de":
    print(f"ERROR: Expected target_language='de', got '{target_lang}'")
    sys.exit(1)

# Step 3: Send a message to next stage (will skip import gate)
print("\nStep 3: Move to CONTACT_CONFIRM (skip import gate)")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "confirm",
        "user_action": {"id": "CONTACT_CONFIRM"}
    }
}, timeout=30)

if resp.status_code != 200:
    print(f"ERROR: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

r = resp.json()
stage = r.get("stage")
metadata = r.get("metadata", {})
target_lang = metadata.get("target_language")

print(f"[✓] Contact stage")
print(f"    Stage: {stage}")
print(f"    target_language: {target_lang}")

if target_lang != "de":
    print(f"ERROR: After CONTACT_CONFIRM, target_language should still be 'de', got '{target_lang}'")
    sys.exit(1)

# Step 4: Move to another stage
print("\nStep 4: Move to EDUCATION_CONFIRM (verify persistence again)")
resp = requests.post(f"{BASE_URL}/cv-tool-call-handler", json={
    "tool_name": "process_cv_orchestrated",
    "params": {
        "session_id": session_id,
        "message": "confirm",
        "user_action": {"id": "EDUCATION_CONFIRM"}
    }
}, timeout=30)

if resp.status_code != 200:
    print(f"ERROR: {resp.status_code}")
    print(resp.text)
    sys.exit(1)

r = resp.json()
stage = r.get("stage")
metadata = r.get("metadata", {})
target_lang = metadata.get("target_language")

print(f"[✓] Education stage")
print(f"    Stage: {stage}")
print(f"    target_language: {target_lang}")

if target_lang != "de":
    print(f"ERROR: After EDUCATION_CONFIRM, target_language should still be 'de', got '{target_lang}'")
    sys.exit(1)

print("\n" + "="*80)
print("[PASS] Metadata persistence working correctly!")
print("       target_language field persists across all API calls")
print("="*80)

sys.exit(0)
