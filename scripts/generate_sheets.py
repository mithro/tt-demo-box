#!/usr/bin/env python3
"""Draw every sheet in ``demobox.drafting.names.SHEETS``.

Each sheet is written to ``output/sheets/<stem>.svg``, rendered to PDF with
the submodule's ``tools.render_svg.to_pdf`` (text as paths, metadata pinned
by ``tools.reproducible``) and to ``output/sheets/previews/<stem>.png``.
Sheets no longer in the set are removed.

Run: make sheets            (or: scripts/generate_sheets.py TDB-LID-P ...)
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import demobox  # noqa: E402,F401  (puts the submodule on sys.path)
from demobox.drafting import names  # noqa: E402
from demobox.drafting import sheetkit  # noqa: E402


def _renderer(kind: str):
    if kind in ("part", "fittings"):
        from demobox.drafting import part_sheet
        return part_sheet.render
    from demobox.drafting import ga_sheet
    return ga_sheet.render


def main(argv: list[str]) -> int:
    want = argv or list(names.SHEETS)
    unknown = [n for n in want if n not in names.SHEETS]
    if unknown:
        raise SystemExit(f"unknown sheet(s) {unknown}; sheets are {list(names.SHEETS)}")
    if not argv:
        keep = {names.svg_path(n).name for n in names.SHEETS}
        keep |= {names.svg_path(n).with_suffix(".pdf").name for n in names.SHEETS}
        for old in sorted(names.OUT.glob("*")):
            if old.is_file() and old.name not in keep:
                old.unlink()
                print(f"removed {old.relative_to(ROOT)}")
        previews = {names.preview_path(n).name for n in names.SHEETS}
        for old in sorted((names.OUT / "previews").glob("*")):
            if old.name not in previews:
                old.unlink()
                print(f"removed {old.relative_to(ROOT)}")
    print(f"version {sheetkit.version()}")
    for n in want:
        t = time.time()
        defn = names.SHEETS[n]
        sheet = _renderer(defn.kind)(defn)
        svg = sheetkit.write(defn, sheet)
        print(f"{n:12s} {defn.size} {sheet.title.scale:6s} {time.time() - t:5.1f} s  "
              f"{svg.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
