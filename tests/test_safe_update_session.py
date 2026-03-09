from __future__ import annotations

import function_app


class _StoreOffloadOk:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def update_session_with_blob_offload(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        self.calls.append((session_id, cv_data, metadata))
        return True

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        raise AssertionError("update_session should not be called when offload succeeds")


class _StoreDirectOnly:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        self.calls.append((session_id, cv_data, metadata))
        return True


class _StoreNeedsShrinkRetry:
    def __init__(self) -> None:
        self.offload_calls: list[tuple[str, dict, dict]] = []

    def update_session_with_blob_offload(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        self.offload_calls.append((session_id, cv_data, metadata))
        if len(self.offload_calls) == 1:
            raise RuntimeError("HttpResponseError: EntityTooLarge")
        return True

    def update_session(self, session_id: str, cv_data: dict, metadata: dict) -> bool:
        raise RuntimeError("HttpResponseError: EntityTooLarge")


def test_safe_update_session_prefers_offload_when_available() -> None:
    store = _StoreOffloadOk()

    ok = function_app._safe_update_session(
        store,
        "sid-1",
        {"full_name": "Jane"},
        {"wizard_stage": "contact"},
    )

    assert ok is True
    assert len(store.calls) == 1


def test_safe_update_session_falls_back_to_direct_update_when_offload_unavailable() -> None:
    store = _StoreDirectOnly()

    ok = function_app._safe_update_session(
        store,
        "sid-2",
        {"full_name": "Jane"},
        {"wizard_stage": "contact"},
    )

    assert ok is True
    assert len(store.calls) == 1


def test_safe_update_session_retries_with_shrunk_metadata_on_entity_too_large(monkeypatch) -> None:
    store = _StoreNeedsShrinkRetry()

    monkeypatch.setattr(
        function_app,
        "_shrink_metadata_for_table",
        lambda meta: {"shrunk": True, "original_keys": sorted(list((meta or {}).keys()))},
    )

    ok = function_app._safe_update_session(
        store,
        "sid-3",
        {"full_name": "Jane"},
        {"event_log": [{"text": "x" * 120000}]},
    )

    assert ok is True
    assert len(store.offload_calls) == 2
    assert store.offload_calls[-1][2].get("shrunk") is True
