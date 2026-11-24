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

def test_names_are_the_one_answer():
    got = list(names.SHEETS)
    for need in ("TDB-GA-P", "TDB-GA-L", "TDB-CUT-L", "TDB-BASE-P", "TDB-DECK-P",
                 "TDB-LID-P", "TDB-DRW-P", "TDB-HGB-P", "TDB-HGL-P", "TDB-CLIP-P",
                 "TDB-PKG-P", "TDB-PIN-P", "TDB-INS-T7", "TDB-INS-C7", "TDB-INS-K7"):
        assert need in got
    assert len(set(got)) == len(got)
    for a in got:
        assert re.fullmatch(r"TDB-[A-Z0-9]+(-[A-Z0-9]+)*", a)
        for b in got:
            assert a == b or not b.startswith(a), f"{a} is a prefix of {b}"
    for n, s in names.SHEETS.items():
        assert s.size == ("A3" if n in ("TDB-GA-P", "TDB-GA-L", "TDB-CUT-L") else "A4")
        assert names.svg_path(n) == ROOT / "output" / "sheets" / f"{s.stem}.svg"
        assert names.name_for(names.svg_path(n)) == n


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


# --- overall dimensions are the solid's (review fix round 1) ---------------------

def _part_records():
    from demobox.drafting import part_sheet as PS
    for n, s in names.SHEETS.items():
        if s.kind == "packing":
            yield n, PS.packing_part(s)
        elif s.kind == "part":
            yield n, PS.BUILDERS[s.subject](s)


def test_part_overall_dims_are_the_solid_bbox():
    """Every part sheet's overall dimensions read the solid's exact bounding
    box (to 0.01), not the discretised outline's: the hinge profiles read
    15.98 and 7.95 for 16.00 and 8.00 when they came off the polylines."""
    from demobox.drafting import part_sheet as PS
    for n, part in _part_records():
        from demobox.drafting.hlr import exact_bbox
        x0, y0, z0, x1, y1, z1 = exact_bbox(part.shape())
        sizes = (x1 - x0, y1 - y0, z1 - z0)
        dims = [d for d in PS.overall_dims(part) if d.text is None]
        assert dims, n
        for d in dims:
            horizontal = d.side in ("top", "bottom")
            value = abs(d.b[0] - d.a[0]) if horizontal else abs(d.b[1] - d.a[1])
            assert min(abs(value - s) for s in sizes) < 0.01, (n, value, sizes)


def test_hinge_profiles_read_their_true_depth():
    from demobox.drafting import part_sheet as PS
    for n, want in (("TDB-HGB-P", 16.0), ("TDB-HGL-P", 8.0)):
        part = PS.BUILDERS[names.SHEETS[n].subject](names.SHEETS[n])
        values = [abs(d.b[0] - d.a[0]) for d in PS.overall_dims(part) if d.side == "bottom"]
        assert any(abs(v - want) < 0.005 for v in values), (n, values)
        assert f">{want:.2f}</text>" in names.svg_path(n).read_text(), n


def _sheet_words(n: str) -> str:
    """Every text line on a generated sheet, joined by spaces."""
    import html
    svg = names.svg_path(n).read_text()
    return " ".join(html.unescape(t) for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg))


@pytest.mark.parametrize("n", ["TDB-GA-P", "TDB-GA-L"])
def test_ga_buy_note_does_not_claim_one_shop(n):
    """M6: a monitor row reads Taobao, so the note may not say every listing
    is an AliExpress item number."""
    words = _sheet_words(n)
    assert "AliExpress item numbers" not in words
    assert "listing numbers or shops" in words


# --- the version stamp (finding 3, R23) -----------------------------------------------

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
