#!/usr/bin/env python3
"""
Diagnostic script to inspect CV Generator session state.

Usage:
    python scripts/diagnose_session.py <session_id>
    python scripts/diagnose_session.py --latest
    python scripts/diagnose_session.py --list
    python scripts/diagnose_session.py --session-id <session_id>  # Extract scenario pack
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Force UTF-8 output
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Set up environment for local development
os.environ.setdefault("AzureWebJobsStorage", "UseDevelopmentStorage=true")

from src.session_store import CVSessionStore


def format_timestamp(ts: str | None) -> str:
    if not ts:
        return "N/A"
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts


def diagnose_session(session_id: str) -> None:
    store = CVSessionStore()
    session = store.get_session(session_id)

    if not session:
        print(f"Session not found: {session_id}")
        return

    print(f"\n{'='*60}")
    print(f"SESSION DIAGNOSIS: {session_id}")
    print(f"{'='*60}\n")

    # Basic info
    print(f"Created:  {format_timestamp(session.get('created_at'))}")
    print(f"Updated:  {format_timestamp(session.get('updated_at'))}")
    print(f"Expires:  {format_timestamp(session.get('expires_at'))}")
    print(f"Version:  {session.get('version')}")

    # CV Data analysis
    cv_data = session.get("cv_data") or {}
    print(f"\n--- CV DATA ---")
    print(f"Full Name:        {cv_data.get('full_name') or '(empty)'}")
    print(f"Email:            {cv_data.get('email') or '(empty)'}")
    print(f"Phone:            {cv_data.get('phone') or '(empty)'}")
    print(f"Address Lines:    {len(cv_data.get('address_lines') or [])}")
    print(f"Photo URL:        {'Yes' if cv_data.get('photo_url') else 'No'} ({len(cv_data.get('photo_url') or '')} chars)")
    print(f"Profile:          {len(cv_data.get('profile') or '')} chars")
    print(f"Work Experience:  {len(cv_data.get('work_experience') or [])} entries")
    print(f"Education:        {len(cv_data.get('education') or [])} entries")
    print(f"Languages:        {len(cv_data.get('languages') or [])} items")
    print(f"IT/AI Skills:     {len(cv_data.get('it_ai_skills') or [])} items")
    print(f"Further Exp:      {len(cv_data.get('further_experience') or [])} entries")
    print(f"Interests:        {len(cv_data.get('interests') or '')} chars")

    # Metadata analysis
    metadata = session.get("metadata") or {}
    print(f"\n--- METADATA ---")
    print(f"Language:         {metadata.get('language') or '(not set)'}")
    print(f"Created From:     {metadata.get('created_from') or '(unknown)'}")

    # Prefill summary
    prefill_summary = metadata.get("prefill_summary") or {}
    if prefill_summary:
        print(f"\n--- PREFILL SUMMARY ---")
        print(f"Has Name:         {prefill_summary.get('has_name')}")
        print(f"Has Email:        {prefill_summary.get('has_email')}")
        print(f"Has Phone:        {prefill_summary.get('has_phone')}")
        print(f"Work Exp Count:   {prefill_summary.get('work_experience_count')}")
        print(f"Education Count:  {prefill_summary.get('education_count')}")
        print(f"Languages Count:  {prefill_summary.get('languages_count')}")
        print(f"Skills Count:     {prefill_summary.get('it_ai_skills_count')}")

    # Confirmation flags
    confirmed_flags = metadata.get("confirmed_flags") or {}
    print(f"\n--- CONFIRMATION STATUS ---")
    print(f"Contact Confirmed:   {confirmed_flags.get('contact_confirmed')}")
    print(f"Education Confirmed: {confirmed_flags.get('education_confirmed')}")
    print(f"Confirmed At:        {format_timestamp(confirmed_flags.get('confirmed_at'))}")

    # Photo blob
    photo_blob = metadata.get("photo_blob")
    if photo_blob:
        print(f"\n--- PHOTO BLOB ---")
        print(f"Container:    {photo_blob.get('container')}")
        print(f"Blob Name:    {photo_blob.get('blob_name')}")
        print(f"Content Type: {photo_blob.get('content_type')}")

    # Unconfirmed prefill data
    docx_prefill = metadata.get("docx_prefill_unconfirmed") or {}
    if docx_prefill:
        print(f"\n--- UNCONFIRMED DOCX PREFILL ---")
        print(f"Full Name:        {docx_prefill.get('full_name') or '(empty)'}")
        print(f"Work Experience:  {len(docx_prefill.get('work_experience') or [])} entries")
        print(f"Education:        {len(docx_prefill.get('education') or [])} entries")
        print(f"Languages:        {len(docx_prefill.get('languages') or [])} items")
        print(f"Skills:           {len(docx_prefill.get('it_ai_skills') or [])} items")

    # Event log
    event_log = metadata.get("event_log") or []
    if event_log:
        print(f"\n--- EVENT LOG ({len(event_log)} events) ---")
        for i, event in enumerate(event_log[-20:]):  # Last 20 events
            event_type = event.get("type", "unknown")
            ts = format_timestamp(event.get("ts"))

            if event_type == "user_message":
                text = (event.get("text") or "")[:80]
                print(f"  [{ts}] USER: {text}...")
            elif event_type == "assistant_message":
                text = (event.get("text") or "")[:80]
                run_summary = event.get("run_summary") or {}
                model_calls = run_summary.get("model_calls", "?")
                steps = run_summary.get("steps") or []
                tool_names = [s.get("tool") for s in steps if s.get("step") == "tool"]
                print(f"  [{ts}] ASSISTANT: {text}...")
                print(f"             Model calls: {model_calls}, Tools: {tool_names}")
            elif event_type == "update_cv_field":
                field_path = event.get("field_path")
                preview = event.get("preview")
                print(f"  [{ts}] UPDATE: {field_path} = {preview}")
            else:
                print(f"  [{ts}] {event_type}")

    # Readiness check
    print(f"\n--- READINESS CHECK ---")
    required_present = {
        "full_name": bool(cv_data.get("full_name", "").strip()) if isinstance(cv_data.get("full_name"), str) else False,
        "email": bool(cv_data.get("email", "").strip()) if isinstance(cv_data.get("email"), str) else False,
        "phone": bool(cv_data.get("phone", "").strip()) if isinstance(cv_data.get("phone"), str) else False,
        "work_experience": bool(cv_data.get("work_experience")) and isinstance(cv_data.get("work_experience"), list),
        "education": bool(cv_data.get("education")) and isinstance(cv_data.get("education"), list),
    }
    contact_ok = bool(confirmed_flags.get("contact_confirmed"))
    education_ok = bool(confirmed_flags.get("education_confirmed"))

    for k, v in required_present.items():
        status = "OK" if v else "MISSING"
        print(f"  {k}: {status}")
    print(f"  contact_confirmed: {'OK' if contact_ok else 'PENDING'}")
    print(f"  education_confirmed: {'OK' if education_ok else 'PENDING'}")

    can_generate = all(required_present.values()) and contact_ok and education_ok
    print(f"\n  CAN GENERATE PDF: {'YES' if can_generate else 'NO'}")

    if not can_generate:
        missing = []
        for k, v in required_present.items():
            if not v:
                missing.append(k)
        if not contact_ok:
            missing.append("contact_not_confirmed")
        if not education_ok:
            missing.append("education_not_confirmed")
        print(f"  Missing: {missing}")

    print(f"\n{'='*60}\n")


def list_sessions() -> None:
    store = CVSessionStore()

    print(f"\n--- ALL SESSIONS ---")

    # This is a workaround since CVSessionStore doesn't have a list method
    # We'll use the underlying table client to list entities
    try:
        from azure.data.tables import TableServiceClient
        conn_str = os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
        if not conn_str:
            print("No storage connection string configured")
            return

        table_service = TableServiceClient.from_connection_string(conn_str)
        table_client = table_service.get_table_client("cvsessions")

        entities = list(table_client.list_entities())

        if not entities:
            print("No sessions found")
            return

        print(f"Found {len(entities)} session(s):\n")

        for entity in entities:
            session_id = entity.get("RowKey")
            created_at = entity.get("created_at", "")
            updated_at = entity.get("updated_at", "")
            version = entity.get("version", 0)

            print(f"  {session_id}")
            print(f"    Created: {format_timestamp(created_at)}")
            print(f"    Updated: {format_timestamp(updated_at)}")
            print(f"    Version: {version}")
            print()

    except Exception as e:
        print(f"Error listing sessions: {e}")


def extract_scenario(session_id: str, output_dir: str = "docs/scenarios") -> None:
    """Extract session data and create a frozen scenario pack."""
    store = CVSessionStore()
    session = store.get_session(session_id)

    if not session:
        print(f"Session not found: {session_id}")
        return

    # Create output directory if needed
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Build scenario pack
    scenario = {
        "scenario_id": session_id,
        "created_at": session.get("created_at"),
        "updated_at": session.get("updated_at"),
        "cv_data": session.get("cv_data") or {},
        "metadata": session.get("metadata") or {},
        "job_posting": session.get("metadata", {}).get("job_posting") or "",
        "artifacts": {
            "photo_blob": session.get("metadata", {}).get("photo_blob"),
            "pdf_refs": session.get("metadata", {}).get("pdf_refs") or [],
            "skills_json_path": None,  # To be filled if available
        },
        "template_version": "CV_template_2pages_2025",
        "dod_commands": [
            f"python scripts/diagnose_session.py {session_id}",
            "npm run pretest",
            "pytest tests/test_*.py -v",
            "npm run test"
        ]
    }

    # Save scenario pack
    scenario_file = output_path / f"scenario_{session_id[:8]}.json"
    with open(scenario_file, "w", encoding="utf-8") as f:
        json.dump(scenario, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"SCENARIO PACK EXTRACTED")
    print(f"{'='*60}")
    print(f"Output: {scenario_file}")
    print(f"Session ID: {session_id}")
    print(f"CV Data Fields: {len(scenario['cv_data'])}")
    print(f"Job Posting: {len(scenario['job_posting'])} chars")
    print(f"Photo Blob: {'Yes' if scenario['artifacts']['photo_blob'] else 'No'}")
    print(f"{'='*60}\n")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    arg = sys.argv[1]

    # Check for --session-id flag
    session_id = None
    extract_mode = False
    
    if "--session-id" in sys.argv:
        idx = sys.argv.index("--session-id")
        if idx + 1 < len(sys.argv):
            session_id = sys.argv[idx + 1]
            extract_mode = True

    if extract_mode and session_id:
        extract_scenario(session_id)
    elif arg == "--list":
        list_sessions()
    elif arg == "--latest":
        # Find the most recent session
        try:
            from azure.data.tables import TableServiceClient
            conn_str = os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
            table_service = TableServiceClient.from_connection_string(conn_str)
            table_client = table_service.get_table_client("cvsessions")

            entities = list(table_client.list_entities())
            if not entities:
                print("No sessions found")
                sys.exit(1)

            # Sort by updated_at descending
            entities.sort(key=lambda e: e.get("updated_at", ""), reverse=True)
            latest = entities[0]
            diagnose_session(latest.get("RowKey"))

        except Exception as e:
            print(f"Error finding latest session: {e}")
            sys.exit(1)
    else:
        diagnose_session(arg)


if __name__ == "__main__":
    main()
