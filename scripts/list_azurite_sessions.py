#!/usr/bin/env python3
"""
list_azurite_sessions.py

Investigation tool for CV-generator-repo Azurite blob storage.
- Lists sessions in cv-sessions container
- Downloads and analyzes session JSON data
- Reports bullet lengths and truncation warnings
- Saves data to tmp/last_session_dump.json

Usage:
  python scripts/list_azurite_sessions.py              # Find last session
  python scripts/list_azurite_sessions.py --session-id <id>  # Specific session
  python scripts/list_azurite_sessions.py --all        # List all sessions
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from azure.storage.blob import BlobServiceClient
except ImportError:
    print("ERROR: azure-storage-blob not found. Install with: pip install azure-storage-blob")
    sys.exit(1)


# Azurite development connection string
AZURITE_CONNECTION_STRING = (
    "DefaultEndpointsProtocol=http;"
    "AccountName=devstoreaccount1;"
    "AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;"
    "BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
)

CV_SESSIONS_CONTAINER = "cv-sessions"
CV_PHOTOS_CONTAINER = "cv-photos"


def get_blob_service_client() -> BlobServiceClient:
    """Connect to Azurite local storage."""
    return BlobServiceClient.from_connection_string(AZURITE_CONNECTION_STRING)


def list_all_sessions(blob_service: BlobServiceClient) -> list[dict]:
    """List all sessions in cv-sessions container."""
    try:
        container_client = blob_service.get_container_client(CV_SESSIONS_CONTAINER)
        blobs = container_client.list_blobs()
        
        sessions = []
        for blob in blobs:
            sessions.append({
                "name": blob.name,
                "last_modified": blob.last_modified,
                "size": blob.size
            })
        
        # Sort by last_modified descending
        sessions.sort(key=lambda x: x["last_modified"], reverse=True)
        return sessions
    except Exception as e:
        print(f"ERROR: Could not list sessions: {e}")
        return []


def download_session_data(blob_service: BlobServiceClient, session_id: str) -> Optional[dict]:
    """Download and parse session JSON data."""
    try:
        container_client = blob_service.get_container_client(CV_SESSIONS_CONTAINER)
        blob_client = container_client.get_blob_client(session_id)
        
        download_stream = blob_client.download_blob()
        content = download_stream.readall()
        
        return json.loads(content)
    except Exception as e:
        print(f"ERROR: Could not download session {session_id}: {e}")
        return None


def analyze_bullet_lengths(session_data: dict) -> dict:
    """Analyze work experience bullet lengths."""
    analysis = {
        "full_name": session_data.get("full_name", "Unknown"),
        "positions": []
    }
    
    work_experience = session_data.get("work_experience", [])
    for i, position in enumerate(work_experience):
        employer = position.get("employer", "Unknown")
        title = position.get("title", "Unknown")
        bullets = position.get("bullets", [])
        
        bullet_info = []
        for j, bullet in enumerate(bullets):
            blen = len(str(bullet))
            warning = ""
            if blen > 200:
                warning = "⚠️ EXCEEDS 200-char hard limit"
            elif blen > 100:
                warning = "⚠️ EXCEEDS 100-char validator limit"
            
            bullet_info.append({
                "index": j,
                "length": blen,
                "warning": warning,
                "text": str(bullet)[:80] + "..." if len(str(bullet)) > 80 else str(bullet)
            })
        
        analysis["positions"].append({
            "index": i,
            "employer": employer,
            "title": title,
            "bullets": bullet_info
        })
    
    return analysis


def print_analysis(analysis: dict, session_id: str, pdf_ref: Optional[str] = None):
    """Print detailed bullet length analysis."""
    print("\n=== SESSION ANALYSIS ===")
    print(f"Session ID: {session_id}")
    if pdf_ref:
        print(f"PDF Ref:    {pdf_ref}")
    print(f"Full Name:  {analysis['full_name']}")
    
    print("\nWork Experience:")
    for pos in analysis["positions"]:
        print(f"\n  Position #{pos['index']}: {pos['title']}, {pos['employer']}")
        for bullet in pos["bullets"]:
            print(f"    - Bullet {bullet['index']}: {bullet['length']} chars {bullet['warning']}")
            if bullet['warning']:
                print(f"      {bullet['text']}")
    
    print("\n" + "="*50)


def save_dump(session_data: dict, analysis: dict, session_id: str):
    """Save session dump to tmp/last_session_dump.json."""
    repo_root = Path(__file__).resolve().parents[1]
    tmp_dir = repo_root / "tmp"
    tmp_dir.mkdir(exist_ok=True)
    
    dump_file = tmp_dir / "last_session_dump.json"
    
    dump = {
        "session_id": session_id,
        "timestamp": datetime.now().isoformat(),
        "analysis": analysis,
        "raw_data": session_data
    }
    
    with open(dump_file, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved to: {dump_file}")
    return dump_file


def main():
    parser = argparse.ArgumentParser(description="List and analyze Azurite CV sessions")
    parser.add_argument("--session-id", help="Specific session ID to analyze")
    parser.add_argument("--all", action="store_true", help="List all sessions")
    args = parser.parse_args()
    
    blob_service = get_blob_service_client()
    
    # List all sessions
    sessions = list_all_sessions(blob_service)
    
    if not sessions:
        print("No sessions found in Azurite storage.")
        print("Make sure Azurite is running and cv-sessions container exists.")
        return
    
    if args.all:
        print(f"\n=== ALL SESSIONS ({len(sessions)}) ===")
        for i, session in enumerate(sessions):
            print(f"{i+1}. {session['name']}")
            print(f"   Last Modified: {session['last_modified']}")
            print(f"   Size: {session['size']} bytes")
        return
    
    # Find target session
    if args.session_id:
        target_id = args.session_id
        print(f"Analyzing session: {target_id}")
    else:
        # Use most recent
        target_id = sessions[0]["name"]
        print(f"Analyzing LAST session: {target_id}")
        print(f"Last Modified: {sessions[0]['last_modified']}")
    
    # Download and analyze
    session_data = download_session_data(blob_service, target_id)
    if not session_data:
        return
    
    analysis = analyze_bullet_lengths(session_data)
    pdf_ref = session_data.get("pdf_ref")
    
    print_analysis(analysis, target_id, pdf_ref)
    save_dump(session_data, analysis, target_id)


if __name__ == '__main__':
    main()
