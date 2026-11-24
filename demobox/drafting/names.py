"""Every sheet: its drawing name, file, size and what it draws.

The one answer, as the submodule's ``tools/layout.py`` is for its sheets: the
generator, the check and the tests all ask here, so they cannot disagree about
the set.

A name is ``TDB-`` (tt-demo-box), a short code for the subject, and the build
route where the drawing belongs to one (``-P`` printed, ``-L`` laser).  No name
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
    kind: Literal["ga", "cutlist", "part", "fittings"]
    #: The route for "ga", "cutlist" and "fittings" (the route's printed
    #: fittings, every one on the sheet); the printed route's part name
    #: (``printed.body.printed_parts``) for "part".
    subject: str
    title: str

    @property
    def stem(self) -> str:
        return self.name.lower()


def _s(name, size, kind, subject, title) -> tuple[str, SheetDef]:
    return name, SheetDef(name, size, kind, subject, title)


#: Reading order: the two general arrangements, the laser cut list, the
#: printed route's parts, then the laser route's printed fittings.
SHEETS: dict[str, SheetDef] = dict((
    _s("TDB-GA-P", "A3", "ga", "printed", "DEMO BOX, PRINTED"),
    _s("TDB-GA-L", "A3", "ga", "laser", "DEMO BOX, LASER-CUT"),
    _s("TDB-CUT-L", "A3", "cutlist", "laser", "LASER CUT LIST"),
    _s("TDB-BASE-P", "A3", "part", "base", "BASE"),
    _s("TDB-LID-P", "A3", "part", "lid", "LID"),
    _s("TDB-PIN-P", "A4", "part", "mt1-pin", "MT1 LOCATING PIN"),
    _s("TDB-FIT-L", "A3", "fittings", "laser", "PRINTED FITTINGS, LASER"),
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
