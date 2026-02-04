from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from azure.core.exceptions import ResourceExistsError, ResourceNotFoundError
from azure.storage.blob import BlobServiceClient, ContentSettings


def _store_mode() -> str:
    # For tests/dev you can force local mode:
    # - CV_PROFILE_STORE_MODE=local
    # Default: blob (if storage conn string is configured).
    mode = str(os.environ.get("CV_PROFILE_STORE_MODE") or "").strip().lower()
    return mode or "blob"


def _get_storage_connection_string() -> str:
    conn_str = os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
    if not conn_str:
        raise ValueError("STORAGE_CONNECTION_STRING or AzureWebJobsStorage not configured")
    return conn_str


def _get_blob_api_version(conn_str: str) -> Optional[str]:
    # Keep aligned with src/blob_store.py to avoid Azurite x-ms-version issues.
    api_version = (os.environ.get("STORAGE_BLOB_API_VERSION") or "").strip()
    if api_version:
        return api_version
    if "UseDevelopmentStorage=true" in conn_str:
        return "2023-11-03"
    return None


def _normalize_lang(lang: Optional[str]) -> str:
    l = str(lang or "").strip().lower()
    if not l:
        return "default"
    # Keep blob paths predictable; reject odd characters.
    safe = "".join(ch for ch in l if ch.isalnum() or ch in ("-", "_"))[:16]
    return safe or "default"


@dataclass(frozen=True)
class StoredProfileRef:
    store: str
    key: str


class CVProfileStore:
    """Key-value store for a user's stable profile artifacts (contact/education/interests/languages)."""

    def get_latest(self, *, user_id: str, target_language: Optional[str] = None) -> Optional[dict]:
        raise NotImplementedError

    def put_latest(self, *, user_id: str, payload: dict, target_language: Optional[str] = None) -> StoredProfileRef:
        raise NotImplementedError


class LocalProfileStore(CVProfileStore):
    def __init__(self, *, root_dir: Optional[str] = None):
        base = root_dir or os.environ.get("CV_PROFILE_STORE_LOCAL_DIR") or str(Path("tmp") / "profile_store")
        self.root = Path(base)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, user_id: str) -> Path:
        return self.root / f"{user_id}.profile_v1.json"

    def _path_lang(self, user_id: str, target_language: Optional[str]) -> Path:
        lang = _normalize_lang(target_language)
        return self.root / f"{user_id}.profile_v1.{lang}.json"

    def get_latest(self, *, user_id: str, target_language: Optional[str] = None) -> Optional[dict]:
        # Prefer per-language artifact if requested; fall back to legacy/default.
        candidates: list[Path] = []
        if target_language:
            candidates.append(self._path_lang(user_id, target_language))
        candidates.append(self._path_lang(user_id, None))
        candidates.append(self._path(user_id))
        p = next((c for c in candidates if c.exists()), None)
        if p is None:
            return None
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8") or "{}")
        except Exception:
            return None

    def put_latest(self, *, user_id: str, payload: dict, target_language: Optional[str] = None) -> StoredProfileRef:
        p = self._path_lang(user_id, target_language)
        p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return StoredProfileRef(store="local", key=str(p))


class BlobProfileStore(CVProfileStore):
    def __init__(self, connection_string: Optional[str] = None, *, container: Optional[str] = None):
        conn_str = connection_string or _get_storage_connection_string()
        self.container = (container or os.environ.get("STORAGE_CONTAINER_PROFILES") or "cv-profiles").strip()
        api_version = _get_blob_api_version(conn_str)
        self.client = (
            BlobServiceClient.from_connection_string(conn_str, api_version=api_version)
            if api_version
            else BlobServiceClient.from_connection_string(conn_str)
        )
        self._ensure_container()

    def _ensure_container(self) -> None:
        try:
            self.client.create_container(self.container)
        except ResourceExistsError:
            return

    def _latest_blob_name(self, user_id: str, target_language: Optional[str]) -> str:
        lang = _normalize_lang(target_language)
        return f"profiles/{user_id}/{lang}/latest_profile_v1.json"

    def get_latest(self, *, user_id: str, target_language: Optional[str] = None) -> Optional[dict]:
        # Prefer per-language artifact; fall back to default, then legacy path.
        blob_names = []
        if target_language:
            blob_names.append(self._latest_blob_name(user_id, target_language))
        blob_names.append(self._latest_blob_name(user_id, None))
        blob_names.append(f"profiles/{user_id}/latest_profile_v1.json")  # legacy

        for blob_name in blob_names:
            blob = self.client.get_blob_client(container=self.container, blob=blob_name)
            try:
                raw = blob.download_blob().readall()
            except ResourceNotFoundError:
                continue
            except Exception:
                # Treat any storage error as cache miss; orchestration must continue.
                return None
            try:
                return json.loads(raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else "{}")
            except Exception:
                return None
        return None

    def put_latest(self, *, user_id: str, payload: dict, target_language: Optional[str] = None) -> StoredProfileRef:
        blob_name = self._latest_blob_name(user_id, target_language)
        blob = self.client.get_blob_client(container=self.container, blob=blob_name)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            blob.upload_blob(
                body,
                overwrite=True,
                content_settings=ContentSettings(content_type="application/json"),
            )
        except Exception:
            # Don't fail the pipeline on caching.
            return StoredProfileRef(store="blob_error", key=f"{self.container}/{blob_name}")
        return StoredProfileRef(store="blob", key=f"{self.container}/{blob_name}")


_PROFILE_STORE: CVProfileStore | None = None


def get_profile_store() -> CVProfileStore:
    global _PROFILE_STORE
    if _PROFILE_STORE is not None:
        return _PROFILE_STORE

    mode = _store_mode()
    if mode == "local":
        _PROFILE_STORE = LocalProfileStore()
        return _PROFILE_STORE

    try:
        _PROFILE_STORE = BlobProfileStore()
        return _PROFILE_STORE
    except Exception:
        # Fallback to local mode if blob isn't configured/reachable (tests/offline dev).
        _PROFILE_STORE = LocalProfileStore()
        return _PROFILE_STORE
