"""
Session storage for CV data using Azure Table Storage
Enables stateful CV processing across conversation turns
"""

import logging
import json
import uuid
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from azure.data.tables import TableServiceClient, TableEntity
from azure.core.exceptions import ResourceNotFoundError, ResourceExistsError
import os
import threading


_CLIENT_CACHE_LOCK = threading.Lock()
_CLIENT_CACHE: dict[str, tuple[TableServiceClient, Any]] = {}
_TABLE_READY: set[str] = set()


class CVSessionStore:
    """Manages CV session data in Azure Table Storage"""
    
    TABLE_NAME = "cvsessions"
    DEFAULT_TTL_HOURS = 24
    EVENT_LOG_MAX_ITEMS = 20
    
    def __init__(self, connection_string: Optional[str] = None):
        """Initialize session store with Azure Table Storage"""
        conn_str = connection_string or os.environ.get("STORAGE_CONNECTION_STRING") or os.environ.get("AzureWebJobsStorage")
        if not conn_str:
            raise ValueError("STORAGE_CONNECTION_STRING or AzureWebJobsStorage not configured")

        # Cache per-process to avoid repeated "create table" probes + connection setup.
        with _CLIENT_CACHE_LOCK:
            cached = _CLIENT_CACHE.get(conn_str)
            if cached is None:
                service_client = TableServiceClient.from_connection_string(conn_str)
                table_client = service_client.get_table_client(self.TABLE_NAME)
                cached = (service_client, table_client)
                _CLIENT_CACHE[conn_str] = cached

        self.service_client, self.table_client = cached
        self._ensure_table_exists_once(conn_str)
    
    def _ensure_table_exists_once(self, conn_str: str):
        """Create table if it doesn't exist (once per process + connection string)."""
        if conn_str in _TABLE_READY:
            return
        try:
            self.service_client.create_table(self.TABLE_NAME)
            logging.info(f"Created table: {self.TABLE_NAME}")
        except ResourceExistsError:
            logging.debug(f"Table {self.TABLE_NAME} already exists")
        with _CLIENT_CACHE_LOCK:
            _TABLE_READY.add(conn_str)
    
    def create_session(self, cv_data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> str:
        """
        Create new CV session with extracted data
        
        Args:
            cv_data: Normalized CV data dictionary
            metadata: Optional metadata (language, source_file, etc.)
        
        Returns:
            session_id: Unique session identifier
        """
        session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        expires_at = now + timedelta(hours=self.DEFAULT_TTL_HOURS)
        
        entity = {
            "PartitionKey": "cv",
            "RowKey": session_id,
            "cv_data_json": json.dumps(cv_data),
            "metadata_json": json.dumps(metadata or {}),
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "version": 1
        }

        self.table_client.create_entity(entity)
        
        logging.info(f"Created session {session_id}, expires at {expires_at.isoformat()}")
        return session_id
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve CV data from session
        
        Args:
            session_id: Session identifier
        
        Returns:
            Dictionary with cv_data and metadata, or None if not found/expired
        """
        try:
            entity = self.table_client.get_entity(partition_key="cv", row_key=session_id)
        except ResourceNotFoundError:
            logging.warning(f"Session {session_id} not found")
            return None
        
        # Check expiration
        expires_at = datetime.fromisoformat(entity.get("expires_at", "1970-01-01T00:00:00"))
        if datetime.utcnow() > expires_at:
            logging.warning(f"Session {session_id} expired at {expires_at.isoformat()}")
            self.delete_session(session_id)
            return None
        
        return {
            "session_id": session_id,
            "cv_data": json.loads(entity["cv_data_json"]),
            "metadata": json.loads(entity.get("metadata_json", "{}")),
            "created_at": entity.get("created_at"),
            "updated_at": entity.get("updated_at"),
            "expires_at": entity.get("expires_at"),
            "version": entity.get("version", 1)
        }
    
    def update_session(self, session_id: str, cv_data: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None) -> bool:
        """
        Update existing session with new CV data
        
        Args:
            session_id: Session identifier
            cv_data: Updated CV data
            metadata: Optional updated metadata
        
        Returns:
            True if updated, False if session not found
        """
        try:
            entity = self.table_client.get_entity(partition_key="cv", row_key=session_id)
        except ResourceNotFoundError:
            logging.warning(f"Session {session_id} not found for update")
            return False
        
        # Update fields
        entity["cv_data_json"] = json.dumps(cv_data)
        if metadata is not None:
            entity["metadata_json"] = json.dumps(metadata)
        entity["updated_at"] = datetime.utcnow().isoformat()
        entity["version"] = entity.get("version", 1) + 1
        
        self.table_client.update_entity(entity, mode="replace")
        logging.info(f"Updated session {session_id}, version {entity['version']}")
        return True
    
    def update_field(
        self,
        session_id: str,
        field_path: str,
        value: Any,
        client_context: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Update specific field in CV data (supports nested paths)

        Args:
            session_id: Session identifier
            field_path: Dot-notation path (e.g., "full_name", "work_experience[0].employer")
            value: New value for the field

        Returns:
            True if updated, False if session not found
        """
        session = self.get_session(session_id)
        if not session:
            return False

        cv_data = session["cv_data"]
        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}

        # Keep logs minimal (avoid dumping personal data).
        value_preview = "(empty)"
        if isinstance(value, str):
            value_preview = f"<str:{len(value)}>"
        elif isinstance(value, list):
            value_preview = f"<list:{len(value)}>"
        elif isinstance(value, dict):
            value_preview = f"<dict:{len(value)}>"
        else:
            value_preview = f"<{type(value).__name__}>"
        logging.debug(f"update_field: path={field_path}, value={value_preview}")

        # Parse field path and update
        parts = field_path.replace("[", ".").replace("]", "").split(".")
        current = cv_data

        for i, part in enumerate(parts[:-1]):
            if part.isdigit():
                idx = int(part)
                if not isinstance(current, list):
                    raise TypeError(
                        f"Invalid path '{field_path}': expected list at '{'.'.join(parts[:i])}', got {type(current).__name__}"
                    )
                # Auto-expand lists for start-from-0 sessions (common for work_experience[0] style updates)
                if idx >= len(current):
                    current.extend({} for _ in range(idx - len(current) + 1))
                current = current[idx]
            else:
                if part not in current:
                    # If the next segment is a numeric index, this key should be a list.
                    next_part = parts[i + 1]
                    current[part] = [] if next_part.isdigit() else {}
                current = current[part]

        # Set final value
        last_key = parts[-1]
        if last_key.isdigit():
            idx = int(last_key)
            if not isinstance(current, list):
                raise TypeError(
                    f"Invalid path '{field_path}': expected list at '{'.'.join(parts[:-1])}', got {type(current).__name__}"
                )
            if idx >= len(current):
                current.extend(None for _ in range(idx - len(current) + 1))
            current[idx] = value
        else:
            current[last_key] = value

        # Log the updated cv_data signature (debug-only).
        try:
            work_exp_count = len(cv_data.get("work_experience", []))
            edu_count = len(cv_data.get("education", []))
            profile_len = len(str(cv_data.get("profile", "")))
            logging.debug(
                f"update_field: after update - work_exp_count={work_exp_count}, edu_count={edu_count}, profile_len={profile_len}"
            )
        except Exception:
            pass

        # Append a bounded event log entry (helps stateless agent keep continuity across turns).
        try:
            event_log = metadata.get("event_log")
            if not isinstance(event_log, list):
                event_log = []

            preview = value_preview
            if isinstance(value, list):
                preview = f"[{len(value)} items]"
            elif isinstance(value, dict):
                preview = f"{{dict with {len(value)} keys}}"

            evt: Dict[str, Any] = {
                "ts": datetime.utcnow().isoformat(),
                "type": "update_cv_field",
                "field_path": field_path,
                "value_type": type(value).__name__,
                "preview": preview,
            }
            if isinstance(client_context, dict) and client_context:
                # Keep only a bounded, non-sensitive context summary.
                evt["client_context_keys"] = list(client_context.keys())[:20]
            event_log.append(evt)

            # Keep only last N events to cap Table Storage size.
            metadata["event_log"] = event_log[-self.EVENT_LOG_MAX_ITEMS :]
        except Exception as e:
            logging.warning(f"update_field: failed to append event_log for session {session_id}: {e}")

        return self.update_session(session_id, cv_data, metadata)

    def append_event(self, session_id: str, event: Dict[str, Any]) -> bool:
        """Append a small event record to session metadata (bounded) without changing CV data."""
        session = self.get_session(session_id)
        if not session:
            return False

        cv_data = session["cv_data"]
        metadata = session.get("metadata") if isinstance(session.get("metadata"), dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}

        try:
            event_log = metadata.get("event_log")
            if not isinstance(event_log, list):
                event_log = []

            out = dict(event or {})
            out.setdefault("ts", datetime.utcnow().isoformat())
            event_log.append(out)
            metadata["event_log"] = event_log[-self.EVENT_LOG_MAX_ITEMS :]
        except Exception as e:
            logging.warning(f"append_event: failed to append event_log for session {session_id}: {e}")
            return False

        return self.update_session(session_id, cv_data, metadata)
    
    def delete_session(self, session_id: str) -> bool:
        """
        Delete session
        
        Args:
            session_id: Session identifier
        
        Returns:
            True if deleted, False if not found
        """
        try:
            self.table_client.delete_entity(partition_key="cv", row_key=session_id)
            logging.info(f"Deleted session {session_id}")
            return True
        except ResourceNotFoundError:
            logging.warning(f"Session {session_id} not found for deletion")
            return False
    
    def cleanup_expired(self) -> int:
        """
        Remove expired sessions
        
        Returns:
            Number of sessions deleted
        """
        now = datetime.utcnow()
        deleted = 0
        
        query = f"PartitionKey eq 'cv' and expires_at lt datetime'{now.isoformat()}'"
        entities = self.table_client.query_entities(query)
        
        for entity in entities:
            self.table_client.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])
            deleted += 1
        
        if deleted > 0:
            logging.info(f"Cleaned up {deleted} expired sessions")
        
        return deleted

    def delete_all_sessions(self) -> int:
        """
        Danger zone: delete all CV sessions (used for explicit reset).
        Returns number of deleted sessions.
        """
        deleted = 0
        for entity in self.table_client.list_entities():
            if entity.get("PartitionKey") == "cv":
                self.table_client.delete_entity(partition_key=entity["PartitionKey"], row_key=entity["RowKey"])
                deleted += 1
        logging.info(f"Deleted {deleted} session(s) via delete_all_sessions()")
        return deleted

    def update_session_with_blob_offload(
        self,
        session_id: str,
        cv_data: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
        *,
        max_table_size: int = 50000  # Conservative limit (Azure Table limit is 64KB per property)
    ) -> bool:
        """
        Update session with automatic blob offloading for large cv_data.
        
        If cv_data exceeds max_table_size, it is stored in blob storage
        and replaced with a reference in the table entity.
        
        Args:
            session_id: Session identifier
            cv_data: Updated CV data (may be large)
            metadata: Optional updated metadata
            max_table_size: Maximum size in bytes before offloading to blob
        
        Returns:
            True if updated, False if session not found
        """
        try:
            entity = self.table_client.get_entity(partition_key="cv", row_key=session_id)
        except ResourceNotFoundError:
            logging.warning(f"Session {session_id} not found for update")
            return False
        
        # Estimate cv_data size
        cv_data_json = json.dumps(cv_data, ensure_ascii=False)
        cv_data_bytes = len(cv_data_json.encode('utf-8'))
        
        if cv_data_bytes > max_table_size:
            # Offload cv_data to blob storage
            logging.info(
                f"CV data size ({cv_data_bytes} bytes) exceeds table limit ({max_table_size} bytes). "
                f"Offloading to blob storage for session {session_id}"
            )
            
            blob_ref = self._offload_cv_data_to_blob(session_id, cv_data)
            
            # Store only a reference in table
            entity["cv_data_json"] = json.dumps({
                "__blob_ref__": blob_ref,
                "__offloaded__": True,
                "size_bytes": cv_data_bytes
            })
            
            # Also add blob reference to metadata for tracking
            if metadata is None:
                metadata_str = entity.get("metadata_json", "{}")
                metadata = json.loads(metadata_str) if metadata_str else {}
            
            metadata["cv_data_blob_ref"] = blob_ref
            metadata["cv_data_offloaded_at"] = datetime.utcnow().isoformat()
        else:
            # Store directly in table (normal path)
            entity["cv_data_json"] = cv_data_json
        
        if metadata is not None:
            entity["metadata_json"] = json.dumps(metadata, ensure_ascii=False)
        
        entity["updated_at"] = datetime.utcnow().isoformat()
        entity["version"] = entity.get("version", 1) + 1
        
        self.table_client.update_entity(entity, mode="replace")
        logging.info(f"Updated session {session_id}, version {entity['version']}")
        return True

    def _offload_cv_data_to_blob(self, session_id: str, cv_data: Dict[str, Any]) -> str:
        """
        Upload cv_data to blob storage and return blob reference.
        
        Args:
            session_id: Session identifier
            cv_data: CV data to offload
        
        Returns:
            Blob reference string (format: 'container/blob_name')
        """
        from .blob_store import CVBlobStore
        
        # Use cv-artifacts container for session data snapshots
        container = os.environ.get("STORAGE_CONTAINER_ARTIFACTS", "cv-artifacts")
        blob_store = CVBlobStore(container=container)
        
        # Create blob name with timestamp
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        blob_name = f"{session_id}/cv_data_{timestamp}.json"
        
        # Upload cv_data as JSON blob
        pointer = blob_store.upload_json_snapshot(
            blob_name=blob_name,
            data=cv_data,
            metadata={
                'session_id': session_id,
                'snapshot_type': 'cv_data_offload',
                'timestamp': timestamp
            }
        )
        
        return f"{pointer.container}/{pointer.blob_name}"

    def get_session_with_blob_retrieval(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get session data, automatically retrieving cv_data from blob if offloaded.
        
        Args:
            session_id: Session identifier
        
        Returns:
            Session data with cv_data restored from blob if necessary, or None if not found
        """
        session = self.get_session(session_id)
        if not session:
            return None
        
        cv_data = session.get("cv_data")
        
        # Check if cv_data was offloaded to blob
        if isinstance(cv_data, dict) and cv_data.get("__offloaded__"):
            blob_ref = cv_data.get("__blob_ref__")
            if blob_ref:
                logging.info(f"Retrieving offloaded cv_data from blob for session {session_id}")
                cv_data = self._retrieve_cv_data_from_blob(blob_ref)
                session["cv_data"] = cv_data
        
        return session

    def _retrieve_cv_data_from_blob(self, blob_ref: str) -> Dict[str, Any]:
        """
        Retrieve cv_data from blob storage.
        
        Args:
            blob_ref: Blob reference string (format: 'container/blob_name')
        
        Returns:
            CV data retrieved from blob
        """
        from .blob_store import CVBlobStore, BlobPointer
        
        parts = blob_ref.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid blob reference format: {blob_ref}")
        
        container, blob_name = parts
        blob_store = CVBlobStore(container=container)
        
        pointer = BlobPointer(container=container, blob_name=blob_name, content_type="application/json")
        return blob_store.download_json_snapshot(pointer)

    def verify_pdf_metadata_persisted(self, session_id: str, pdf_ref: str) -> tuple[bool, list[str]]:
        """
        Verify that PDF metadata was successfully persisted to session storage.
        
        Args:
            session_id: Session identifier
            pdf_ref: PDF reference to verify
        
        Returns:
            Tuple of (success: bool, errors: list[str])
        """
        errors = []
        
        try:
            session = self.get_session_with_blob_retrieval(session_id)
            if not session:
                errors.append(f"Session {session_id} not found after PDF generation")
                return False, errors
            
            metadata = session.get("metadata", {})
            
            # Check pdf_generated flag
            if not metadata.get("pdf_generated"):
                errors.append("pdf_generated flag not set in metadata")
            
            # Check pdf_refs contains the new PDF
            pdf_refs = metadata.get("pdf_refs", {})
            if not isinstance(pdf_refs, dict):
                errors.append(f"pdf_refs is not a dict: {type(pdf_refs)}")
            elif pdf_ref not in pdf_refs:
                errors.append(f"PDF reference '{pdf_ref}' not found in pdf_refs. Available: {list(pdf_refs.keys())}")
            else:
                # Verify PDF ref has required fields
                pdf_entry = pdf_refs[pdf_ref]
                required_fields = ["container", "blob_name", "created_at", "sha256", "size_bytes"]
                missing = [f for f in required_fields if f not in pdf_entry]
                if missing:
                    errors.append(f"PDF entry missing fields: {missing}")
            
            return len(errors) == 0, errors
        
        except Exception as exc:
            errors.append(f"Verification failed with exception: {exc}")
            return False, errors
