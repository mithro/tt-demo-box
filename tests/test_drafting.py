"""The drawings: hidden-line projection, the sheet names, the sheet check,
and the generated set (``make sheets``)."""

import importlib.util
import re
from pathlib import Path

import cadquery as cq
import pytest

from demobox.drafting import names
from demobox.drafting.hlr import Projection, project

ROOT = Path(__file__).resolve().parent.parent


def _check_sheets():
    spec = importlib.util.spec_from_file_location("check_sheets",
                                                  ROOT / "scripts" / "check_sheets.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _bbox(polylines):
    xs = [x for pl in polylines for x, _ in pl]
    ys = [y for pl in polylines for _, y in pl]
    return min(xs), min(ys), max(xs), max(ys)


def _box(x, y, z, dx, dy, dz) -> cq.Shape:
    return cq.Solid.makeBox(dx, dy, dz, cq.Vector(x, y, z))


# --- hlr -------------------------------------------------------------------------

def test_project_box_front_is_10_by_30():
    p = project(_box(0, 0, 0, 10, 20, 30), "front")
    assert isinstance(p, Projection)
    x0, y0, x1, y1 = _bbox(p.visible)
    assert x1 - x0 == pytest.approx(10.0, abs=1e-6)
    assert y1 - y0 == pytest.approx(30.0, abs=1e-6)
    assert p.hidden == []


@pytest.mark.parametrize("view,want", [
    # front: from the visitor (-Y), X right, Z up
    ("front", (1.0, 3.0, 11.0, 33.0)),
    # side: from the left (-X), placed right of the front (first angle); the
    # visitor's side is on the right, so across is -Y
    ("side", (-22.0, 3.0, -2.0, 33.0)),
    # plan: from above, X right, Y up (the hinge at the top)
    ("plan", (1.0, 2.0, 11.0, 22.0)),
])
def test_project_axes(view, want):
    p = project(_box(1, 2, 3, 10, 20, 30), view)
    assert _bbox(p.visible) == pytest.approx(want, abs=1e-6)


def test_project_hidden_and_chord():
    """A blind hole from the back is hidden from the front; its circle is
    discretised finely (0.1 mm chord) and comes out round."""
    solid = _box(0, 0, 0, 20, 20, 20).cut(
        cq.Solid.makeCylinder(4.0, 10.0, cq.Vector(10, 20, 10), cq.Vector(0, -1, 0)))
    p = project(solid, "front")
    assert _bbox(p.visible) == pytest.approx((0, 0, 20, 20), abs=1e-6)
    pts = [pt for pl in p.hidden for pt in pl]
    assert pts, "the hole should show as hidden detail"
    r = [((x - 10) ** 2 + (y - 10) ** 2) ** 0.5 for x, y in pts]
    assert min(r) == pytest.approx(4.0, abs=0.11) and max(r) == pytest.approx(4.0, abs=0.11)
    assert len(pts) >= 30


# --- names -------------------------------------------------------------------------

#: The compact box's sheet set, in reading order.
SHEET_SET = ("TDB-GA-P", "TDB-GA-L", "TDB-CUT-L", "TDB-BASE-P", "TDB-LID-P", "TDB-PIN-P",
             "TDB-FIT-L")


def test_sheet_set_exact():
    """Exactly the compact box's seven sheets: the two general arrangements,
    the cut list, the printed route's three parts and the laser route's
    printed fittings."""
    got = list(names.SHEETS)
    assert got == list(SHEET_SET)
    for a in got:
        assert re.fullmatch(r"TDB-[A-Z0-9]+(-[A-Z0-9]+)*", a)
        for b in got:
            assert a == b or not b.startswith(a), f"{a} is a prefix of {b}"
    for n, s in names.SHEETS.items():
        assert s.size == ("A4" if n == "TDB-PIN-P" else "A3")
        assert names.svg_path(n) == ROOT / "output" / "sheets" / f"{s.stem}.svg"
        assert names.name_for(names.svg_path(n)) == n
    assert not (ROOT / "demobox" / "drafting" / "insert_sheet.py").exists()


def test_part_sheets_draw_each_routes_printed_parts():
    """The printed route's part sheets draw its ``printed_parts``, one each;
    TDB-FIT-L draws every one of the laser route's printed fittings."""
    from demobox.drafting import part_sheet as PS
    from demobox.laser import fittings as LF
    from demobox.layout import ROUTES, layout
    from demobox.printed import body as B
    printed = {s.subject for s in names.SHEETS.values() if s.kind == "part"}
    assert printed == set(B.printed_parts(layout(ROUTES["printed"])))
    fit = names.SHEETS["TDB-FIT-L"]
    drawn = [p.key for p in PS.fitting_parts(fit)]
    assert drawn == list(LF.printed_parts(layout(ROUTES["laser"])))


# --- check_sheets ----------------------------------------------------------------

_SVG = ('<?xml version="1.0" encoding="UTF-8"?>\n<svg xmlns="http://www.w3.org/2000/svg" '
        'version="1.1" width="297mm" height="210mm" viewBox="0 0 297 210">\n{}\n</svg>\n')


def _text(x, y, s, cap=2.5):
    return (f'<text x="{x}" y="{y}" font-family="DejaVu Sans Condensed" '
            f'font-size="{cap / 0.729:.4f}" fill="#000000" text-anchor="start">{s}</text>')


def test_check_sheets_flags_collision_small_text_and_outside():
    cs = _check_sheets()
    clean = _SVG.format(_text(50, 50, "CLEAN") + _text(50, 80, "APART"))
    assert cs.sheet_problems(clean) == []
    bad = _SVG.format(_text(50, 50, "OVERLAP") + _text(52, 50.5, "OVERLAP"))
    assert any("overlap" in p for p in cs.sheet_problems(bad))
    tiny = _SVG.format(_text(50, 50, "TINY", cap=1.8))
    assert any("under" in p for p in cs.sheet_problems(tiny))
    out = _SVG.format(_text(293, 50, "OUTSIDE"))
    assert any("outside" in p for p in cs.sheet_problems(out))
    # A4 frame: x 20..285; "PROJECTION" ran across its right-hand line
    across = _SVG.format(_text(276, 150, "PROJECTION"))
    assert any("crosses the drawing frame" in p for p in cs.sheet_problems(across))
    geo = _SVG.format(_text(50, 50, "CROSSED") +
                      '<polyline points="40,49 80,49" fill="none" stroke="#000000" '
                      'stroke-width="0.5"/>')
    assert any("through the text" in p for p in cs.sheet_problems(geo))


# --- the generated set (make sheets) -----------------------------------------------

def test_every_sheet_is_generated():
    for n in names.SHEETS:
        svg = names.svg_path(n)
        assert svg.exists(), f"{svg} missing: run make sheets"
        assert svg.with_suffix(".pdf").exists(), f"{n}: no PDF"
        assert names.preview_path(n).exists(), f"{n}: no preview"
        assert f">{n}</text>" in svg.read_text(), f"{n}: drawing number not on the sheet"
    on_disk = {p.stem for p in (ROOT / "output" / "sheets").glob("*.svg")}
    assert on_disk == {s.stem for s in names.SHEETS.values()}


def test_generated_sheets_pass_the_check():
    cs = _check_sheets()
    assert cs.main() == 0


# --- the parts list ------------------------------------------------------------------

def _assembly_count(route: str, part: str) -> int:
    """How many of a made part the closed assembly holds: the part's own
    name, or its name with a ``-<where>`` suffix (``magnet-block-lid-1``)."""
    from demobox.printed import body as B
    return sum(1 for n, _, _ in B.assembly(route, 0.0, False)
               if n == part or n.startswith(part + "-"))


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_ga_parts_list_matches_hardware(route):
    """The GA parts list is the route's ``printed_parts`` (counted in its
    assembly) and its ``hardware``, each once with its count: nothing is
    typed in by hand."""
    from demobox.drafting import ga_sheet as G
    from demobox.laser import fittings as LF
    from demobox.laser import panels as P
    from demobox.layout import ROUTES, layout
    from demobox.printed import body as B
    lay = layout(ROUTES[route])
    rows, _ = G.parts_rows(route, lay)
    by_part = {}
    for item, qty, part, ref in rows:
        assert part not in by_part, f"{part} listed twice"
        by_part[part] = (qty, ref)
    hw = B.hardware(lay) if route == "printed" else LF.hardware(lay, lay.wall)
    for what, n in hw.items():
        assert by_part[what] == (str(n), "bought"), what
    made = B.printed_parts(lay) if route == "printed" else LF.printed_parts(lay, lay.wall)
    for key in made:
        assert by_part[key][0] == str(_assembly_count(route, key)), key
    if route == "laser":
        assert by_part["knuckles-base"][0] == "1"
        assert by_part["magnet-block"] == ("4", "TDB-FIT-L")
        assert by_part["plywood panels, 3 mm"] == (str(len(P.panels(lay, lay.wall))),
                                                   "TDB-CUT-L")
    else:
        assert {k: by_part[k] for k in made} == {
            "base": ("1", "TDB-BASE-P"), "lid": ("1", "TDB-LID-P"),
            "mt1-pin": ("1", "TDB-PIN-P")}
    # every row's item number is its place
    assert [r[0] for r in rows] == [str(i) for i in range(1, len(rows) + 1)]


# --- overall dimensions are the solid's ---------------------------------------------

def _part_records():
    from demobox.drafting import part_sheet as PS
    for n, s in names.SHEETS.items():
        if s.kind == "part":
            yield n, PS.BUILDERS[s.subject](s)
        elif s.kind == "fittings":
            for p in PS.fitting_parts(s):
                yield f"{n} {p.key}", p


def test_part_overall_dims_are_the_solid_bbox():
    """Every part sheet's overall dimensions read the solid's exact bounding
    box (to 0.01), not the discretised outline's."""
    from demobox.drafting import part_sheet as PS
    from demobox.drafting.hlr import exact_bbox
    seen = 0
    for n, part in _part_records():
        x0, y0, z0, x1, y1, z1 = exact_bbox(part.shape())
        sizes = (x1 - x0, y1 - y0, z1 - z0)
        dims = [d for d in PS.overall_dims(part) if d.text is None]
        assert dims, n
        for d in dims:
            horizontal = d.side in ("top", "bottom")
            value = abs(d.b[0] - d.a[0]) if horizontal else abs(d.b[1] - d.a[1])
            assert min(abs(value - s) for s in sizes) < 0.01, (n, value, sizes)
        seen += 1
    assert seen == 3 + 4


# --- what the generated sheets say ----------------------------------------------------

def _sheet_words(n: str) -> str:
    """Every text line on a generated sheet, joined by spaces."""
    import html
    svg = names.svg_path(n).read_text()
    return " ".join(html.unescape(t) for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg))


#: A ruling ID (R15, R16a) or a review "finding": the ledger they point at is
#: not part of the repo.  A radius is always written with its decimals (R4.00).
RULING = re.compile(r"\bR\d+(?![.\d])|finding", re.IGNORECASE)


def test_no_ruling_ids_on_sheets():
    """No sheet, and no drafting source, cites a ruling ID or a review finding."""
    for n in names.SHEETS:
        hits = RULING.findall(_sheet_words(n))
        assert not hits, (n, hits)
    for src in (ROOT / "demobox" / "drafting").glob("*.py"):
        for i, line in enumerate(src.read_text().splitlines(), 1):
            assert not RULING.search(line), f"{src.name}:{i}: {line.strip()}"


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_ga_sheet_says_how_the_box_goes_together(route):
    """The GA notes: the closed size and volume (the layout's), the tape, the
    board's pins, the bank lifting out, the stop and the rod."""
    from demobox.layout import LID_OPEN_DEG, ROUTES, layout
    lay = layout(ROUTES[route])
    o, lid = lay.outer, lay.lid_outer
    words = _sheet_words("TDB-GA-" + route[0].upper())
    h = o.size[2] + lid.size[2]
    assert f"{o.size[0]:.2f} x {o.size[1]:.2f} x {h:.2f}" in words
    assert f"{o.size[0] * o.size[1] * h / 1e6:.2f} L" in words
    assert "double-sided foam tape" in words
    assert "MT2 pin + loose MT1 pin" in words
    assert "lifts out with the lid open" in words
    assert f"{LID_OPEN_DEG:g} deg" in words
    assert "pressed in from the right side face" in words
    assert "drawer" not in words.lower() and "screw" not in words.lower()
    assert "4 magnets, 6 x 3 mm" in words
    if route == "laser":
        assert "3 mm rods" in words
    else:
        from demobox.printed import body as B
        made = B.printed_parts(lay)
        assert f"{len(made)} printed parts: {', '.join(made)}." in words


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_ga_rod_length_is_the_hardware_lists(route):
    """The hinge rod reads the same, to one place, in the GA note and in the
    parts list (they once said 40.8 and 41)."""
    from demobox.laser import fittings as LF
    from demobox.layout import ROUTES, layout
    from demobox.printed import body as B
    from demobox.shared import hinge as H
    lay = layout(ROUTES[route])
    hw = B.hardware(lay) if route == "printed" else LF.hardware(lay, lay.wall)
    keys = [k for k in hw if "(hinge pin" in k]
    assert len(keys) == 1
    rod = re.match(r"(\S+ mm steel rod x \d+\.\d mm) \(hinge pin", keys[0]).group(1)
    words = _sheet_words("TDB-GA-" + route[0].upper())
    assert f"knuckles on one {rod}, pressed in" in words
    assert words.count(rod) == 2, words.count(rod)     # the note and the parts list
    # every hinge rod length on the route's sheets: the same figure
    sheets = ["TDB-GA-" + route[0].upper()] + (["TDB-LID-P"] if route == "printed"
                                                else ["TDB-FIT-L"])
    board = f"{LF.board_pin_length(lay):.1f}" if route == "laser" else None
    want = f"{H.pin_length(lay):.1f}"
    for n in sheets:
        found = [v for v in re.findall(r"3 mm (?:rod )?x (\d+(?:\.\d+)?) mm",
                                       _sheet_words(n)) if v != board]
        assert found and set(found) == {want}, (n, found)


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_ga_sheet_lists_the_hardware(route):
    from demobox.laser import fittings as LF
    from demobox.layout import ROUTES, layout
    from demobox.printed import body as B
    lay = layout(ROUTES[route])
    hw = B.hardware(lay) if route == "printed" else LF.hardware(lay, lay.wall)
    words = _sheet_words("TDB-GA-" + route[0].upper())
    for what in hw:
        assert what in words, what


def test_base_sheet_dimensions_its_features():
    """The base sheet dimensions the plinth, the pins, the notch and the
    magnet pockets."""
    from demobox.layout import ROUTES, layout
    lay = layout(ROUTES["printed"])
    words = _sheet_words("TDB-BASE-P")
    pl, n = lay.plinth, lay.hinge_notch
    for v in (pl.x1 - pl.x0, pl.y1 - pl.y0, n.x1 - n.x0, lay.pins["MT2"].cx,
              lay.pins["MT2"].cy, lay.lid_catch[0].cx, lay.lid_catch[1].cx):
        assert f"{v:.2f}" in words, v
    for word in ("PLINTH", "MT2", "MT1", "NOTCH", "MAGNET"):
        assert word in words, word


def test_lid_sheet_dimensions_its_features():
    """The lid sheet shows the tray, the knuckles and the magnet pockets."""
    from demobox.layout import ROUTES, layout
    from demobox.shared import hinge as H
    lay = layout(ROUTES["printed"])
    words = _sheet_words("TDB-LID-P")
    for k in H.knuckle_plan(lay):
        if k.part == "lid":
            assert f"{k.x1 - k.x0:.2f}" in words, k
    for word in ("KNUCKLE", "MAGNET", "tape"):
        assert word in words, word
    assert "TRAY" in words


def test_fit_sheet_names_every_fitting():
    from demobox.laser import fittings as LF
    from demobox.layout import ROUTES, layout
    words = _sheet_words("TDB-FIT-L")
    for key in LF.printed_parts(layout(ROUTES["laser"])):
        assert key.upper() in words, key


# --- the version stamp -----------------------------------------------------------

def _git(root, *args):
    import subprocess
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid",
                        "PATH": "/usr/bin:/bin", "HOME": str(root)})


def test_stamp_follows_the_sources_not_the_docs(tmp_path):
    """Doc, README and output commits leave the stamp alone; a change to
    demobox/, scripts/, the Makefile or the submodule pin moves it."""
    from demobox.drafting import sheetkit as K
    r = tmp_path / "repo"
    (r / "demobox").mkdir(parents=True)
    (r / "scripts").mkdir()
    (r / "output").mkdir()
    (r / "vendor" / "fpgas.online-mechanical").mkdir(parents=True)   # an unfetched submodule
    (r / "demobox" / "a.py").write_text("A = 1\n")
    (r / "scripts" / "s.py").write_text("pass\n")
    (r / "Makefile").write_text("all:\n")
    (r / "README.md").write_text("readme\n")
    _git(r, "init", "-q")
    _git(r, "update-index", "--add", "--cacheinfo",
         "160000,1111111111111111111111111111111111111111,vendor/fpgas.online-mechanical")
    _git(r, "add", "demobox", "scripts", "Makefile", "README.md")
    _git(r, "commit", "-q", "-m", "one")

    def v():
        K.version.cache_clear()
        return K.version(r)

    first = v()
    assert re.fullmatch(r"[0-9a-f]{%d}" % K.STAMP_LEN, first), first
    (r / "README.md").write_text("readme, edited\n")
    (r / "output" / "x.svg").write_text("<svg/>\n")
    _git(r, "add", "README.md", "output")
    _git(r, "commit", "-q", "-m", "docs and outputs only")
    assert v() == first
    (r / "demobox" / "a.py").write_text("A = 2\n")
    assert v() == first + "+"                     # uncommitted source change
    _git(r, "commit", "-q", "-am", "source")
    second = v()
    assert second not in (first, first + "+")
    (r / "Makefile").write_text("all: x\n")
    _git(r, "commit", "-q", "-am", "make")
    third = v()
    assert third != second
    _git(r, "update-index", "--cacheinfo",
         "160000,2222222222222222222222222222222222222222,vendor/fpgas.online-mechanical")
    _git(r, "commit", "-q", "-m", "bump the submodule")
    assert v() != third
    K.version.cache_clear()


def test_stamp_is_order_independent_and_short():
    from demobox.drafting import sheetkit as K
    a = K.stamp({"demobox": "1" * 40, "Makefile": "2" * 40})
    assert a == K.stamp({"Makefile": "2" * 40, "demobox": "1" * 40})
    assert len(a) == K.STAMP_LEN and a != K.stamp({"demobox": "1" * 40, "Makefile": "3" * 40})
