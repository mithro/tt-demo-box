#!/usr/bin/env python3
"""Write README.md's generated sections.

Each sits between ``<!-- <name>:begin -->`` and ``<!-- <name>:end -->``:

* ``unconfirmed``: the UNCONFIRMED list, from ``verify.py``'s output;
* ``size``: the closed size and volume of each route (``layout``, rounded by
  ``geom.mm`` as the sheets are);
* ``rods``: the hinge rod's length in each route (``hinge.pin_length``);
* ``hardware-printed``: the printed route's bought hardware
  (``demobox.printed.body.hardware``);
* ``hardware-laser``: the laser route's (``demobox.laser.fittings.hardware``).

``--check`` changes nothing and exits 1 if any section is out of date
(``make check`` runs it).

Run: make readme
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
README = ROOT / "README.md"


def _markers(name: str) -> tuple[str, str]:
    return f"<!-- {name}:begin -->", f"<!-- {name}:end -->"


def unconfirmed() -> list[str]:
    out = subprocess.run([sys.executable, str(ROOT / "verify.py")], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    lines = out.splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("UNCONFIRMED ("))
    items, what = [], None
    for line in lines[start + 1:]:
        m = re.match(r"\s+--\s+(.*\S)\s*$", line)
        if m:
            what = m.group(1)
        elif what and line.strip() and not line.startswith("PASS"):
            items.append(f"- **{what}**: {line.strip()}")
            what = None
    head = lines[start].rstrip(":")
    if len(items) != int(re.search(r"\((\d+)", head).group(1)):
        raise SystemExit(f"parsed {len(items)} items but verify.py says: {head}")
    return [f"{head}.", ""] + items


def table(hw: dict[str, int]) -> list[str]:
    """A hardware list as a Markdown table, in the list's own order."""
    return ["| Qty | Part |", "|---:|---|"] + [f"| {n} | {k} |" for k, n in hw.items()]


def hardware_printed() -> list[str]:
    import demobox  # noqa: F401  (puts the submodule on sys.path)
    from demobox.layout import ROUTES, layout
    from demobox.printed import body
    return table(body.hardware(layout(ROUTES["printed"])))


def hardware_laser() -> list[str]:
    import demobox  # noqa: F401
    from demobox.laser import fittings
    from demobox.layout import ROUTES, layout
    t = ROUTES["laser"]
    return table(fittings.hardware(layout(t), t))


#: The size table's route labels.
ROUTE_TITLES = {"printed": "3D printed, {wall:g} mm walls ({bed} mm bed)",
                "laser": "Laser-cut {wall:g} mm plywood ({bed} mm bed)"}


def size() -> list[str]:
    """The closed box per route: W x D x H (base + lid) and its volume."""
    import demobox  # noqa: F401
    from demobox.geom import mm
    from demobox.layout import LASER_BED, PRINT_BED, ROUTES, layout
    beds = {"printed": PRINT_BED, "laser": LASER_BED}
    rows = ["| Route | Closed (W x D x H) | Volume |", "|---|---|---|"]
    for route, wall in ROUTES.items():
        lay = layout(wall)
        o, lid = lay.outer, lay.lid_outer
        h = o.size[2] + lid.size[2]
        bed = " x ".join(f"{v:g}" for v in beds[route])
        rows.append(f"| {ROUTE_TITLES[route].format(wall=wall, bed=bed)} | {mm(o.size[0])} x "
                    f"{mm(o.size[1])} x {mm(h)} mm | {o.size[0] * o.size[1] * h / 1e6:.2f} L |")
    return rows


def rods() -> list[str]:
    """The hinge rod per route, as the hardware lists give it."""
    import demobox  # noqa: F401
    from demobox.layout import PIN_ROD_D, ROUTES, layout
    from demobox.shared import hinge as H
    lengths = ", ".join(f"{H.pin_length(layout(w)):.1f} mm {r}" for r, w in ROUTES.items())
    return [f"The hinge rod is {PIN_ROD_D:g} mm steel rod ({lengths}), pressed in from the "
            f"right-hand side face until flush; its last {H.PRESS_LEN:g} mm is a press fit."]


SECTIONS = {"size": size, "rods": rods, "unconfirmed": unconfirmed,
            "hardware-printed": hardware_printed, "hardware-laser": hardware_laser}


def rewrite(text: str, made: dict[str, list[str]]) -> str:
    """``text`` with each named section's lines replaced by ``made[name]``."""
    for name, lines in made.items():
        begin, end = _markers(name)
        if text.count(begin) != 1 or text.count(end) != 1:
            raise SystemExit(f"README.md needs exactly one {begin} ... {end} pair")
        a, b = text.index(begin) + len(begin), text.index(end)
        text = text[:a] + "\n" + "\n".join(lines) + "\n" + text[b:]
    return text


def main(argv: list[str]) -> int:
    text = README.read_text()
    made = {name: make() for name, make in SECTIONS.items()}
    new = rewrite(text, made)
    if "--check" in argv:
        stale = [n for n in made if rewrite(text, {n: made[n]}) != text]
        if stale:
            print(f"README.md is out of date ({', '.join(stale)}): run `make readme`")
            return 1
        print("README.md's generated sections are up to date")
        return 0
    README.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
