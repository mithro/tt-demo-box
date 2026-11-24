"""Locate the repo and put the fpgas.online-mechanical submodule on sys.path.

The submodule's modules import as top-level ``tools`` and ``tinytapeout``.
"""

import sys
from pathlib import Path

ROOT: Path = Path(__file__).resolve().parent.parent
VENDOR: Path = ROOT / "vendor" / "fpgas.online-mechanical"

if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))
