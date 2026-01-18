from __future__ import annotations

import sys
from pathlib import Path

# Ensure package import works when running tests without installation.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
