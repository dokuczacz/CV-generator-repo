#!/usr/bin/env python3
"""
Diagnostic tool: measure session metadata size and identify components exceeding Azure Table Storage 32KB limit.

Usage:
    python tests/diagnose_session_size.py <session_id>
    
    Example: python tests/diagnose_session_size.py d74bfb01-10c0-4427-b9d5-beb39ace6666
"""

import json
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.session_store import CVSessionStore


def format_size(size_bytes: int) -> str:
    """Format byte size as human-readable string."""
    for unit in ["B", "KB", "MB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}GB"


def diagnose_session_size(session_id: str) -> None:
    """
    Load session and measure:
    - Total metadata size
    - Size of each top-level metadata field
    - Character count of each field (UTF-16 encoded, as Azure Table Storage uses)
    """
    store = CVSessionStore()
    session = store.get_session(session_id)
    
    if not session:
        print(f"❌ Session {session_id} not found.")
        return
    
    print(f"\n📊 Session Size Diagnosis: {session_id}")
    print("=" * 80)
    
    metadata = session.get("metadata", {})
    if not isinstance(metadata, dict):
        print("❌ Metadata is not a dict, skipping analysis.")
        return
    
    # Total size
    metadata_json = json.dumps(metadata)
    total_chars_utf16 = len(metadata_json) * 2  # UTF-16 encoding (worst case: 2 bytes per char)
    total_chars_utf8 = len(metadata_json)
    
    print(f"\n📋 Metadata Summary:")
    print(f"  Total fields: {len(metadata)}")
    print(f"  Total size (UTF-8): {format_size(total_chars_utf8)}")
    print(f"  Total size (UTF-16): {format_size(total_chars_utf16)}")
    print(f"  Azure Table Storage limit: 32 KB = 32,768 bytes")
    
    if total_chars_utf16 > 32768:
        print(f"  ⚠️  EXCEEDS LIMIT by {format_size(total_chars_utf16 - 32768)}")
    else:
        print(f"  ✅ Within limit (margin: {format_size(32768 - total_chars_utf16)})")
    
    # Per-field breakdown
    print(f"\n📁 Field Size Breakdown (top to bottom, largest first):")
    field_sizes = []
    
    for key, value in metadata.items():
        value_json = json.dumps(value) if not isinstance(value, str) else value
        size_utf8 = len(value_json)
        size_utf16 = size_utf8 * 2
        field_sizes.append((key, size_utf8, size_utf16, value_json[:200]))
    
    field_sizes.sort(key=lambda x: x[2], reverse=True)
    
    for key, size_utf8, size_utf16, preview in field_sizes[:20]:  # Top 20 fields
        status = "⚠️" if size_utf16 > 5000 else "✅"
        print(f"\n  {status} {key}:")
        print(f"     UTF-8: {format_size(size_utf8)} | UTF-16: {format_size(size_utf16)}")
        if len(preview) > 0:
            sanitized = preview.replace("\n", "\\n")[:100]
            print(f"     Preview: {sanitized}...")
    
    # Specific high-value targets for compression
    print(f"\n🎯 Compression Targets:")
    
    if "job_posting_text" in metadata:
        jp_size = len(json.dumps(metadata["job_posting_text"])) * 2
        print(f"  • job_posting_text: {format_size(jp_size)}")
        print(f"    → Reduce from 20,000 chars → 10,000 chars (saves {format_size((20000 - 10000) * 2)})")
    
    if "work_experience_proposal_block" in metadata:
        wp_size = len(json.dumps(metadata["work_experience_proposal_block"])) * 2
        print(f"  • work_experience_proposal_block: {format_size(wp_size)}")
        print(f"    → Consider storing in blob storage instead")
    
    if "skills_proposal_block" in metadata:
        sp_size = len(json.dumps(metadata["skills_proposal_block"])) * 2
        print(f"  • skills_proposal_block: {format_size(sp_size)}")
        print(f"    → Currently: {metadata['skills_proposal_block']}")
        print(f"    → ✅ Verify it actually contains 5-8 items per section")
        if isinstance(metadata['skills_proposal_block'], dict):
            it_ai = metadata['skills_proposal_block'].get('it_ai_skills', [])
            tech_op = metadata['skills_proposal_block'].get('technical_operational_skills', [])
            print(f"    → Actual content: IT/AI: {len(it_ai)} items, Technical/Operational: {len(tech_op)} items")
    
    if "docx_prefill_unconfirmed" in metadata:
        dpu_size = len(json.dumps(metadata["docx_prefill_unconfirmed"])) * 2
        print(f"  • docx_prefill_unconfirmed: {format_size(dpu_size)}")
        print(f"    → Consider storing in blob storage instead")
    
    print("\n" + "=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    session_id = sys.argv[1]
    diagnose_session_size(session_id)
