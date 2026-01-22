import sys
from pathlib import Path

# Ensure repo root is importable so `import src...` works regardless of pytest import mode.
ROOT = Path(__file__).resolve().parents[1]
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)
