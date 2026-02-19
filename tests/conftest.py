import sys
import os
import json
from pathlib import Path
import pytest

# Ensure repo root is importable so `import src...` works regardless of pytest import mode.
ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


@pytest.fixture(scope="session", autouse=True)
def load_local_settings():
    """
    Auto-load local.settings.json environment variables for all tests.
    This ensures tests can find STORAGE_CONNECTION_STRING and other Azure settings.
    """
    local_settings_path = ROOT / "local.settings.json"
    if local_settings_path.exists():
        with open(local_settings_path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            values = settings.get("Values", {})
            for key, value in values.items():
                # Only set if not already set (allow override from real env)
                if key not in os.environ:
                    os.environ[key] = str(value)
