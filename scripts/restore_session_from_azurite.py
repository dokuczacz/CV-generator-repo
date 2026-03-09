#!/usr/bin/env python3
"""Restore a missing session row in Azure Table (Azurite) from existing artifact blobs.

Usage:
  python scripts/restore_session_from_azurite.py --session-id <uuid>
  python scripts/restore_session_from_azurite.py --session-id <uuid> --expires-at 2099-12-31T23:59:59
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime

from azure.data.tables import TableServiceClient
from azure.storage.blob import BlobServiceClient


def _conn_str() -> str:
    conn = os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
    if conn:
        return conn
    return "UseDevelopmentStorage=true"


def _blob_api_version(conn: str) -> str | None:
    forced = (os.environ.get("STORAGE_BLOB_API_VERSION") or "").strip()
    if forced:
        return forced
    if "UseDevelopmentStorage=true" in conn:
        return "2023-11-03"
    return None


def _choose_latest_cv_blob(blob_service: BlobServiceClient, session_id: str) -> tuple[str, int]:
    container = "cv-artifacts"
    container_client = blob_service.get_container_client(container)

    prefix = f"{session_id}/"
    candidates = []
    for blob in container_client.list_blobs(name_starts_with=prefix):
        if "/cv_data_" not in f"/{blob.name}":
            continue
        candidates.append(blob)

    if not candidates:
        raise RuntimeError(f"No cv_data artifacts found for session {session_id} in {container}")

    candidates.sort(key=lambda b: b.last_modified, reverse=True)
    latest = candidates[0]
    return f"{container}/{latest.name}", int(getattr(latest, "size", 0) or 0)


def _choose_latest_metadata_blob(blob_service: BlobServiceClient, session_id: str) -> str | None:
    container = "cv-artifacts"
    container_client = blob_service.get_container_client(container)

    prefix = f"{session_id}/"
    candidates = []
    for blob in container_client.list_blobs(name_starts_with=prefix):
        if "metadata_heavy_" in blob.name:
            candidates.append(blob)

    if not candidates:
        return None

    candidates.sort(key=lambda b: b.last_modified, reverse=True)
    latest = candidates[0]
    return f"{container}/{latest.name}"


def restore_session(session_id: str, expires_at: str) -> None:
    conn = _conn_str()

    api_version = _blob_api_version(conn)
    blob_service = (
        BlobServiceClient.from_connection_string(conn, api_version=api_version)
        if api_version
        else BlobServiceClient.from_connection_string(conn)
    )
    cv_blob_ref, cv_size = _choose_latest_cv_blob(blob_service, session_id)
    metadata_blob_ref = _choose_latest_metadata_blob(blob_service, session_id)

    metadata = {
        "cv_data_blob_ref": cv_blob_ref,
        "cv_data_offloaded_at": datetime.utcnow().isoformat(),
        "restored_from_blob": True,
        "restored_at": datetime.utcnow().isoformat(),
    }
    if metadata_blob_ref:
        metadata["metadata_blob_ref"] = metadata_blob_ref

    now = datetime.utcnow().isoformat()
    entity = {
        "PartitionKey": "cv",
        "RowKey": session_id,
        "cv_data_json": json.dumps(
            {
                "__blob_ref__": cv_blob_ref,
                "__offloaded__": True,
                "size_bytes": cv_size,
            },
            ensure_ascii=False,
        ),
        "metadata_json": json.dumps(metadata, ensure_ascii=False),
        "created_at": now,
        "updated_at": now,
        "expires_at": expires_at,
        "version": 1,
    }

    table_service = TableServiceClient.from_connection_string(conn)
    table_client = table_service.get_table_client("cvsessions")
    table_client.upsert_entity(entity=entity, mode="replace")

    print("RESTORE_OK")
    print(f"session_id={session_id}")
    print(f"cv_blob_ref={cv_blob_ref}")
    if metadata_blob_ref:
        print(f"metadata_blob_ref={metadata_blob_ref}")
    print(f"expires_at={expires_at}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--expires-at", default="2099-12-31T23:59:59")
    args = parser.parse_args()

    restore_session(session_id=args.session_id, expires_at=args.expires_at)


if __name__ == "__main__":
    main()
