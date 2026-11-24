#!/usr/bin/env python3
"""Write README.md's generated sections.

Each sits between ``<!-- <name>:begin -->`` and ``<!-- <name>:end -->``:

* ``unconfirmed``: the UNCONFIRMED list, from ``verify.py``'s output;
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


SECTIONS = {"unconfirmed": unconfirmed, "hardware-printed": hardware_printed,
            "hardware-laser": hardware_laser}


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
