import os
import shutil
from pathlib import Path


def test_fast_profile_apply_local_store_smoke(monkeypatch):
    # Force local store mode for deterministic tests (no Azurite dependency).
    tmp_root = Path("tmp") / "test_profile_store"
    shutil.rmtree(tmp_root, ignore_errors=True)
    tmp_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CV_PROFILE_STORE_MODE", "local")
    monkeypatch.setenv("CV_PROFILE_STORE_LOCAL_DIR", str(tmp_root))

    import src.profile_store as profile_store

    # Reset store singleton so env vars take effect in this test.
    profile_store._PROFILE_STORE = None  # type: ignore[attr-defined]

    from function_app import _maybe_apply_fast_profile, _stable_profile_payload, _stable_profile_user_id

    cv_data = {
        "full_name": "Jan Kowalski",
        "email": "jan.kowalski@example.com",
        "phone": "+41 76 123 45 67",
        "address_lines": ["Zurich"],
        "education": [{"title": "MSc", "institution": "ETH", "date_range": "2010-2012"}],
        "interests": "cycling, hiking",
        "languages": [{"name": "English", "level": "C1"}],
        "language": "en",
    }
    meta = {"target_language": "de", "language": "de"}

    user_id = _stable_profile_user_id(cv_data, meta)
    assert isinstance(user_id, str) and len(user_id) == 64

    payload = _stable_profile_payload(cv_data=cv_data, meta=meta)
    profile_store.get_profile_store().put_latest(user_id=user_id, payload=payload, target_language="de")

    # New session-like data: should get filled from cache (same email -> same user_id).
    cv_data2 = {"email": "jan.kowalski@example.com"}
    meta2 = {"language": "en", "target_language": "de"}

    out_cv, out_meta, applied = _maybe_apply_fast_profile(
        cv_data=cv_data2,
        meta=meta2,
        client_context={"fast_path_profile": True},
    )

    assert applied is True
    assert out_cv.get("full_name") == "Jan Kowalski"
    assert out_cv.get("interests") == "cycling, hiking"
    assert isinstance(out_cv.get("education"), list) and out_cv["education"]
    assert out_meta.get("target_language") == "de"
    assert out_meta.get("fast_profile_lang") == "de"


def test_profile_store_language_variants(monkeypatch):
    # Force local store mode for deterministic tests (no Azurite dependency).
    tmp_root = Path("tmp") / "test_profile_store_lang"
    shutil.rmtree(tmp_root, ignore_errors=True)
    tmp_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("CV_PROFILE_STORE_MODE", "local")
    monkeypatch.setenv("CV_PROFILE_STORE_LOCAL_DIR", str(tmp_root))

    import src.profile_store as profile_store

    profile_store._PROFILE_STORE = None  # type: ignore[attr-defined]
    store = profile_store.get_profile_store()
    user_id = "user123"

    store.put_latest(user_id=user_id, payload={"schema_version": "profile_v1", "saved_at": "t1", "target_language": "en"}, target_language="en")
    store.put_latest(user_id=user_id, payload={"schema_version": "profile_v1", "saved_at": "t2", "target_language": "de"}, target_language="de")

    got_de = store.get_latest(user_id=user_id, target_language="de")
    got_en = store.get_latest(user_id=user_id, target_language="en")

    assert isinstance(got_de, dict) and got_de.get("target_language") == "de"
    assert isinstance(got_en, dict) and got_en.get("target_language") == "en"
