#!/usr/bin/env python3
"""Write the UNCONFIRMED list into README.md from ``verify.py``'s output.

The list sits between the ``<!-- unconfirmed:begin -->`` and
``<!-- unconfirmed:end -->`` markers.  ``--check`` changes nothing and exits 1
if the README is out of date (``make check`` runs it).

Run: make readme
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
BEGIN, END = "<!-- unconfirmed:begin -->", "<!-- unconfirmed:end -->"


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


def main(argv: list[str]) -> int:
    text = README.read_text()
    a, b = text.index(BEGIN) + len(BEGIN), text.index(END)
    new = text[:a] + "\n" + "\n".join(unconfirmed()) + "\n" + text[b:]
    if "--check" in argv:
        if new != text:
            print("README.md's UNCONFIRMED list is out of date: run `make readme`")
            return 1
        print("README.md's UNCONFIRMED list is up to date")
        return 0
    README.write_text(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
