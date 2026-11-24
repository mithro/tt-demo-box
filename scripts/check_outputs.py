#!/usr/bin/env python3
"""Prove ``output/`` is what the sources build.

Rebuilds the STEP, STL, DXF, SVG, PDF and preview PNG files into
``tmp/check-outputs/`` (the same tree as ``output/``) and compares each with
the committed copy byte for byte; the builds are reproducible (see
``tools.reproducible``).  A missing, extra or different file fails.

``output/renders/*.png`` is not compared: Blender's Cycles renders are noisy
and do not reproduce byte for byte.

Run: make check-outputs
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import demobox  # noqa: E402,F401  (puts the submodule on sys.path)
from demobox.drafting import names  # noqa: E402

COMMITTED = ROOT / "output"
WORK = ROOT / "tmp" / "check-outputs"
#: Directories under output/ that are not rebuilt here.
NOT_REBUILT = {"renders"}


def rebuild() -> None:
    """Each exporter in a process of its own, as ``make outputs`` runs them:
    cadquery numbers an assembly's STEP occurrences from a counter that lives
    in the process, so a second assembly written in the same process would
    differ from the committed file."""
    import generate_sheets
    if WORK.exists():
        shutil.rmtree(WORK)
    (WORK / "sheets" / "previews").mkdir(parents=True)
    for script, out in (("export_printed.py", "printed"), ("export_laser.py", "laser")):
        subprocess.run([sys.executable, str(ROOT / "scripts" / script),
                        "--out", str(WORK / out)], check=True)
    names.OUT = WORK / "sheets"          # svg_path / preview_path read this
    if generate_sheets.main([]) != 0:
        raise SystemExit("generate_sheets failed")


def files(base: Path) -> dict[str, Path]:
    return {p.relative_to(base).as_posix(): p for p in sorted(base.rglob("*"))
            if p.is_file() and p.relative_to(base).parts[0] not in NOT_REBUILT
            and ".cache" not in p.relative_to(base).parts}


def main() -> int:
    rebuild()
    have, built = files(COMMITTED), files(WORK)
    problems = [f"output/{n}: committed but no longer built" for n in sorted(have.keys() - built.keys())]
    problems += [f"output/{n}: built but not committed" for n in sorted(built.keys() - have.keys())]
    problems += [f"output/{n}: differs from a rebuild (see tmp/check-outputs/{n})"
                 for n in sorted(have.keys() & built.keys())
                 if have[n].read_bytes() != built[n].read_bytes()]
    for p in problems:
        print(p)
    if problems:
        print(f"{len(problems)} problem(s): run `make outputs sheets` and commit output/")
        return 1
    print(f"output/ is up to date: {len(have)} files identical to a rebuild "
          "(output/renders not compared: Cycles noise)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
