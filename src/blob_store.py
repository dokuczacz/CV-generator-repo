from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings


@dataclass(frozen=True)
class BlobPointer:
    container: str
    blob_name: str
    content_type: str


def _get_storage_connection_string() -> str:
    conn_str = os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
    if not conn_str:
        raise ValueError("STORAGE_CONNECTION_STRING or AzureWebJobsStorage not configured")
    return conn_str


def _get_blob_api_version(conn_str: str) -> Optional[str]:
    # Azurite often lags Azure Storage API versions. The Python SDK may default to a
    # newer x-ms-version that Azurite rejects (e.g. "2026-02-06").
    # Allow overriding via env var; default to a commonly-supported version for local Azurite.
    api_version = (os.environ.get("STORAGE_BLOB_API_VERSION") or "").strip()
    if api_version:
        return api_version
    if "UseDevelopmentStorage=true" in conn_str:
        return "2023-11-03"
    return None


class CVBlobStore:
    """Minimal Blob helper for session-attached assets (e.g., photos)."""

    def __init__(self, connection_string: Optional[str] = None, *, container: Optional[str] = None):
        conn_str = connection_string or _get_storage_connection_string()
        self.container = (container or os.environ.get("STORAGE_CONTAINER_PHOTOS") or "cv-photos").strip()
        api_version = _get_blob_api_version(conn_str)
        self.client = BlobServiceClient.from_connection_string(conn_str, api_version=api_version) if api_version else BlobServiceClient.from_connection_string(conn_str)
        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            self.client.create_container(self.container)
        except ResourceExistsError:
            return

    def upload_bytes(self, *, blob_name: str, data: bytes, content_type: str) -> BlobPointer:
        blob = self.client.get_blob_client(container=self.container, blob=blob_name)
        blob.upload_blob(
            data,
            overwrite=True,
            content_settings=ContentSettings(content_type=content_type),
        )
        return BlobPointer(container=self.container, blob_name=blob_name, content_type=content_type)

    def download_bytes(self, pointer: BlobPointer) -> bytes:
        blob = self.client.get_blob_client(container=pointer.container, blob=pointer.blob_name)
        try:
            return blob.download_blob().readall()
        except ResourceNotFoundError as exc:
            raise FileNotFoundError(f"Blob not found: {pointer.container}/{pointer.blob_name}") from exc

    def delete_prefix(self, prefix: str) -> int:
        """
        Delete all blobs under a given prefix. Returns count deleted.
        """
        deleted = 0
        container_client = self.client.get_container_client(self.container)
        for blob in container_client.list_blobs(name_starts_with=prefix):
            container_client.delete_blob(blob)
            deleted += 1
        return deleted

    def purge_all(self) -> int:
        """
        Delete all blobs in the container. Returns count deleted.
        """
        deleted = 0
        container_client = self.client.get_container_client(self.container)
        for blob in container_client.list_blobs():
            container_client.delete_blob(blob)
            deleted += 1
        return deleted
