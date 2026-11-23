#!/usr/bin/env python3
"""Check the generated sheets: text collisions, small text, things outside
the frame, lines through text, and every drawing name in its title block.

Built on the submodule's ``tools/check_sheets.py`` (``boxes``, ``lines``,
``overlap``, ``box_hits_line``, ``side_gap``, ``drawing_no_cell``): the same
text metrics the layout used, recovered from the SVG.  Two things are added
for these sheets, whose views are hidden-line projections drawn as
polylines:

* a view's edges (``<polyline>``, black or phantom) running through a piece
  of text, which the submodule's line test cannot see (it reads ``<line>``
  only);
* the ISO 5457 centring marks, which run 5 mm into the frame, as lines no
  text may sit on.

Every sheet in ``demobox.drafting.names.SHEETS`` must exist; every problem
is printed, and the exit status is 1 if there is any, so ``make check``
fails on it.

Run: make check-sheets
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import demobox  # noqa: E402,F401  (puts the submodule on sys.path)
from tools import check_sheets as T  # noqa: E402
from tools.drafting import style  # noqa: E402

from demobox.drafting import names  # noqa: E402

POLY_RE = re.compile(r'<polyline points="([^"]+)" fill="none" stroke="([#\w]+)"')
#: Polylines that are drawing: the views' edges (black) and phantom outlines.
GEOMETRY = {style.C_LINE, style.C_PHANTOM}
#: A balloon on these sheets: radius and colour of ``sheetkit.Balloon``.
BALLOON_R = 3.2
CIRCLE_RE = T.CIRCLE_RE


def _segments(svg: str):
    for m in POLY_RE.finditer(svg):
        if m.group(2) not in GEOMETRY:
            continue
        pts = [tuple(float(v) for v in p.split(",")) for p in m.group(1).split()]
        for a, b in zip(pts, pts[1:]):
            yield (*a, *b)


def _centring(svg: str, w: float, h: float):
    """The four centring marks where they run inside the frame, as segments
    (sheet px = mm, Y down).  Outside it they cross the zone strip, and the
    middle zone letter of an odd number of rows sits on them by the frame's
    own design."""
    f = style.FRAME_MARGIN
    fx = style.FILING_MARGIN
    return [(w / 2, f, w / 2, f + 5.0), (w / 2, h - f - 5.0, w / 2, h - f),
            (fx, h / 2, fx + 5.0, h / 2), (w - f - 5.0, h / 2, w - f, h / 2)]


def sheet_problems(svg: str) -> list[str]:
    """Everything wrong with one sheet's SVG text."""
    page_w = float(re.search(r'width="([\d.]+)mm"', svg).group(1))
    page_h = float(re.search(r'height="([\d.]+)mm"', svg).group(1))
    trim = style.TRIM_MARGIN
    items = T.boxes(svg)
    rules = T.vertical_rules(T.all_lines(svg))
    segs = list(T.lines(svg)) + list(_segments(svg)) + _centring(svg, page_w, page_h)
    out: list[str] = []
    for i, a in enumerate(items):
        if a[5] < T.MIN_TEXT_MM:
            out.append(f"text {a[4]!r} is {a[5]:.2f} mm, under the {T.MIN_TEXT_MM} mm floor")
        if a[0] < trim or a[2] > page_w - trim or a[1] < trim or a[3] > page_h - trim:
            out.append(f"text {a[4]!r} at ({a[0]:.1f},{a[1]:.1f}) lies outside the frame")
        for b in items[i + 1:]:
            ov = T.overlap(a, b)
            if ov > T.OVERLAP_TOL:
                out.append(f"text {a[4]!r} and {b[4]!r} overlap by {ov:.2f} mm near "
                           f"({max(a[0], b[0]):.1f},{max(a[1], b[1]):.1f})")
                continue
            gap = T.side_gap(a, b, rules)
            if gap is not None and gap < T.MIN_WORD_GAP:
                out.append(f"text {a[4]!r} and {b[4]!r} are {gap:.2f} mm apart and read as "
                           f"one word, near ({max(a[0], b[0]):.1f},{max(a[1], b[1]):.1f})")
    for a in items:
        for seg in segs:
            run = T.box_hits_line(a[:4], seg, tol=0.5)
            if run > 1.0:
                out.append(f"a line runs {run:.2f} mm through the text {a[4]!r} at "
                           f"({a[0]:.1f},{a[1]:.1f})")
                break
    for m in CIRCLE_RE.finditer(svg):
        cx, cy, r = (float(v) for v in m.groups()[:3])
        if abs(r - BALLOON_R) > 0.01 or m.group(5) != style.C_HIGHLIGHT:
            continue
        for a in items:
            if a[0] <= cx <= a[2] and a[1] <= cy <= a[3]:
                continue
            bite = T.circle_bites_box((cx, cy, r), a[:4])
            if bite > T.OVERLAP_TOL:
                out.append(f"a balloon at ({cx:.1f},{cy:.1f}) covers {bite:.2f} mm of "
                           f"the text {a[4]!r}")
    return out


def name_problems() -> list[str]:
    """Every name is its own, no name is a prefix of another, and each sheet
    carries its own in a DRAWING NO cell it fits."""
    out: list[str] = []
    got = list(names.SHEETS)
    for a in got:
        for b in got:
            if a != b and b.startswith(a):
                out.append(f"{a} is a prefix of {b}")
    for n in got:
        svg = names.svg_path(n)
        if not svg.exists():
            out.append(f"{svg.relative_to(ROOT)} is missing: run make sheets")
            continue
        text = svg.read_text()
        cell = T.drawing_no_cell(T.boxes(text), T.vertical_rules(T.all_lines(text)))
        if cell is None:
            out.append(f"{n}: no DRAWING NO cell")
            continue
        value, room = cell
        if value != n:
            out.append(f"{n}: the DRAWING NO cell reads {value!r}")
        width = style.text_width(n, style.T_MIN, bold=True)
        if width > room:
            out.append(f"{n}: the name needs {width:.2f} mm of the cell's {room:.2f} mm")
    stray = {p.stem for p in names.OUT.glob("*.svg")} - {s.stem for s in names.SHEETS.values()}
    out += [f"output/sheets/{s}.svg is not a sheet in names.SHEETS" for s in sorted(stray)]
    return out


def main() -> int:
    total = 0
    for n in names.SHEETS:
        svg = names.svg_path(n)
        if not svg.exists():
            continue                 # reported by name_problems
        text = svg.read_text()
        problems = sheet_problems(text)
        if problems:
            total += len(problems)
            print(f"{n}: {len(problems)} problem(s)")
            for line in problems:
                print(f"    {line}")
        else:
            print(f"{n}: clean ({len(T.boxes(text))} text elements)")
    for line in name_problems():
        print(f"names: {line}")
        total += 1
    print(f"\n{total} problem(s) across {len(names.SHEETS)} sheets")
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
