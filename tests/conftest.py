"""Make scripts/scaffold.py importable as `scaffold` for the test suite."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "scaffold.py"

_spec = importlib.util.spec_from_file_location("scaffold", SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["scaffold"] = _mod
assert _spec.loader is not None
_spec.loader.exec_module(_mod)
