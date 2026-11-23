"""Every sheet: its drawing name, file, size and what it draws.

The one answer, as the submodule's ``tools/layout.py`` is for its sheets: the
generator, the check and the tests all ask here, so they cannot disagree about
the set.

A name is ``TDB-`` (tt-demo-box), a short code for the subject, and the build
route where the drawing belongs to one (``-P`` printed, ``-L`` laser).  The
insert sheets carry the monitor instead: an insert is the same part for both
routes but the bezel's outline, and is drawn for the printed route.  No name
is a prefix of another (``check_sheets.py`` tests it), so quoting one never
points at two.

The file stem is the name in lower case, so a drawing found on paper is found
on disk by what it says in its title block.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from demobox._paths import ROOT

OUT = ROOT / "output" / "sheets"


@dataclass(frozen=True)
class SheetDef:
    name: str
    size: Literal["A3", "A4"]
    kind: Literal["ga", "cutlist", "part", "packing", "insert"]
    #: The route for "ga"/"cutlist", the printed part's name for "part", the
    #: monitor key for "insert", "" for "packing" (every bank).
    subject: str
    title: str

    @property
    def stem(self) -> str:
        return self.name.lower()


def _s(name, size, kind, subject, title) -> tuple[str, SheetDef]:
    return name, SheetDef(name, size, kind, subject, title)


#: Reading order: the two general arrangements, the laser cut list, the
#: printed parts, then the monitor inserts.
SHEETS: dict[str, SheetDef] = dict((
    _s("TDB-GA-P", "A3", "ga", "printed", "DEMO BOX, PRINTED"),
    _s("TDB-GA-L", "A3", "ga", "laser", "DEMO BOX, LASER-CUT"),
    _s("TDB-CUT-L", "A3", "cutlist", "laser", "LASER CUT LIST"),
    _s("TDB-BASE-P", "A4", "part", "base", "BASE TUB"),
    _s("TDB-DECK-P", "A4", "part", "deck", "DECK"),
    _s("TDB-LID-P", "A4", "part", "lid", "LID"),
    _s("TDB-DRW-P", "A4", "part", "drawer", "DRAWER"),
    _s("TDB-HGB-P", "A4", "part", "hinge-base", "HINGE, BASE HALF"),
    _s("TDB-HGL-P", "A4", "part", "hinge-lid", "HINGE, LID HALF"),
    _s("TDB-CLIP-P", "A4", "part", "bezel-clip", "BEZEL CLIP"),
    _s("TDB-PKG-P", "A4", "packing", "", "BATTERY PACKING"),
    _s("TDB-PIN-P", "A4", "part", "mt1-pin", "MT1 LOCATING PIN"),
    _s("TDB-INS-T7", "A4", "insert", "taobao-tim", "MONITOR INSERT, T7"),
    _s("TDB-INS-C7", "A4", "insert", "car-7-aliexpress", "MONITOR INSERT, C7"),
    _s("TDB-INS-K7", "A4", "insert", "kit-at070tn92", "MONITOR INSERT, K7"),
))


def svg_path(name: str) -> Path:
    return OUT / f"{SHEETS[name].stem}.svg"


def preview_path(name: str) -> Path:
    return OUT / "previews" / f"{SHEETS[name].stem}.png"


def name_for(svg: Path) -> str:
    """The drawing name of a rendered sheet, from its path."""
    for n, s in SHEETS.items():
        if s.stem == Path(svg).stem:
            return n
    raise KeyError(f"{svg} is not a sheet in names.SHEETS")
