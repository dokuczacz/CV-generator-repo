"""
Validate golden structured outputs against the strict JSON schema.

Usage:
  python scripts/validate_structured_output.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import validate
from jsonschema.exceptions import ValidationError

# Ensure local src is on path for direct script execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from src.structured_response import CVAssistantResponse, CV_ASSISTANT_RESPONSE_SCHEMA


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    golden_dir = root / "tmp" / "structured_output_golden"
    files = sorted(golden_dir.glob("*.json"))
    if not files:
        print("No golden files found.")
        return 1

    schema = CV_ASSISTANT_RESPONSE_SCHEMA["schema"]
    ok = True
    for file in files:
        data = json.loads(file.read_text(encoding="utf-8"))
        try:
            validate(instance=data, schema=schema)
            CVAssistantResponse.parse_obj(data)
            print(f"[OK] {file.name}")
        except ValidationError as e:
            ok = False
            print(f"[FAIL] {file.name}: {e.message}")
        except Exception as e:
            ok = False
            print(f"[FAIL] {file.name}: {e}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
