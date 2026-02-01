"""Mariusz Horodecki CV test data (deterministic).

Source of truth: `samples/extracted_cv.json` (extracted from the DOCX sample).

This module enriches the extracted data with a deterministic inline photo so that
visual regression tests don't depend on local files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXTRACTED_JSON = _REPO_ROOT / "samples" / "extracted_cv.json"

# 1x1 transparent PNG, deterministic (keeps tests hermetic).
_DEFAULT_PHOTO_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMB/"
    "ax2nS8AAAAASUVORK5CYII="
)


def _load_extracted_cv() -> Dict[str, Any]:
    raw = _EXTRACTED_JSON.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise TypeError(f"Expected dict in {_EXTRACTED_JSON}, got {type(data).__name__}")
    return data


CV_DATA: Dict[str, Any] = _load_extracted_cv()

# Make visual tests deterministic and avoid missing elements.
CV_DATA.setdefault("photo_url", _DEFAULT_PHOTO_URL)

# Render template uses `language` for footer labels; keep stable.
CV_DATA.setdefault("language", "en")
