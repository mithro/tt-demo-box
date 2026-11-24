"""scripts/export_scene.py: the Blender scene manifests.

``export_scene.export(out)`` writes one JSON manifest per render plus the STL
files and the test-pattern image they reference.  The manifests are checked
here; the renders themselves are looked at by eye (``make renders``).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import export_scene as ES  # noqa: E402

from demobox.checks import pigtail_path  # noqa: E402
from demobox.layout import LID_OPEN_DEG, ROUTES, layout  # noqa: E402
from demobox.printed import body  # noqa: E402
from demobox.shared.solids import BANK_OUT_LIFT  # noqa: E402

#: Written under the repo's git-ignored tmp/ (house rule: never /tmp).
OUT = ROOT / "tmp" / "test-scene"

EXPECTED = {f"{r}-{v}" for r in ("printed", "laser")
            for v in ("closed", "open-front", "open-back", "bank-out")} | {"laser-flatpack"}


def _matrix(entry) -> list[list[float]]:
    t = entry["transform"] if isinstance(entry, dict) else entry
    assert len(t) == 16
    return [t[0:4], t[4:8], t[8:12], t[12:16]]


def _lid_angle(m) -> float:
    """Opening angle (degrees) of a lid-frame transform: the lid turns by
    -angle about +X (``Layout.lid_location``)."""
    assert abs(m[0][0] - 1.0) < 1e-9 and abs(m[1][0]) < 1e-9 and abs(m[2][0]) < 1e-9
    return -math.degrees(math.atan2(m[2][1], m[1][1]))


def _apply(m16, p):
    m = _matrix(m16)
    return tuple(sum(m[r][c] * v for c, v in enumerate((*p, 1.0))) for r in range(3))


def _bb(solid):
    b = solid.BoundingBox()
    return (b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax)


# --- names and the Makefile ----------------------------------------------------------

def test_render_names():
    assert set(ES.RENDERS) == EXPECTED
    assert len(ES.RENDERS) == 9
    v = ES.VIEWS
    assert (v["closed"].lid_deg, v["closed"].bank_out) == (0.0, False)
    for name in ("open-front", "open-back"):
        assert (v[name].lid_deg, v[name].bank_out) == (LID_OPEN_DEG, False)
    assert (v["bank-out"].lid_deg, v["bank-out"].bank_out) == (LID_OPEN_DEG, True)


def test_makefile_renders_match():
    """``make renders`` loops over the Makefile's RENDERS: the same list."""
    text = (ROOT / "Makefile").read_text().replace("\\\n", " ")
    line = next(ln for ln in text.splitlines() if ln.startswith("RENDERS :="))
    assert line.split(":=", 1)[1].split() == list(ES.RENDERS)


def test_makefile_renders_fail_loudly():
    """Review finding: a crashed render reported success.  Blender exits
    non-zero on a Python error, each PNG is deleted before it is rendered (no
    stale image survives a failure), and a log without "rendered in" fails."""
    text = (ROOT / "Makefile").read_text()
    blender = next(ln for ln in text.splitlines() if ln.startswith("BLENDER :="))
    assert "--python-exit-code 1" in blender
    recipe = text.split("\nrenders:", 1)[1].split("\n\n", 1)[0]
    assert "rm -f output/renders/$$r.png" in recipe
    assert recipe.index("rm -f output/renders/$$r.png") < recipe.index("$(BLENDER)")
    assert 'grep -q "rendered in" tmp/render-$$r.log' in recipe


# --- frames --------------------------------------------------------------------------

def test_lid_transform_matches_layout():
    lay = layout(ROUTES["printed"])
    m = ES.frame_matrix(lay, "lid", LID_OPEN_DEG, False)
    assert _lid_angle(_matrix(m)) == pytest.approx(LID_OPEN_DEG)
    # The STLs hold the lid parts shut, in the base frame, so the transform
    # is the turn about the hinge axis: the axis stays put, and a shut lid
    # point (lid frame (y, z) + the axis) lands where Layout._open_yz (the
    # profile the fit checks use) puts it.
    hy, hz = lay.hinge_axis
    assert _apply(m, (0.0, hy, hz)) == pytest.approx((0.0, hy, hz))
    y, z = -150.0, 20.0
    assert _apply(m, (0.0, hy + y, hz + z))[1:] == pytest.approx(
        lay._open_yz(y, z, LID_OPEN_DEG))
    assert ES.frame_matrix(lay, "lid", 0.0, False) == pytest.approx(ES.IDENTITY)
    assert ES.frame_matrix(lay, "base", LID_OPEN_DEG, True) == pytest.approx(ES.IDENTITY)


def test_bank_transform_lifts_the_bank_out():
    """The bank frame: still in the bay, or lifted BANK_OUT_LIFT clear of the
    rim (``assembly(..., bank_out=True)``), straight up."""
    lay = layout(ROUTES["printed"])
    assert ES.frame_matrix(lay, "bank", LID_OPEN_DEG, False) == pytest.approx(ES.IDENTITY)
    m = ES.frame_matrix(lay, "bank", LID_OPEN_DEG, True)
    lift = lay.rim_z + BANK_OUT_LIFT - lay.bank_bay.z0
    assert m == pytest.approx([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, lift, 0, 0, 0, 1])


# --- the parts ----------------------------------------------------------------------

@pytest.mark.parametrize("route", ["printed", "laser"])
def test_scene_parts_match_assembly(route):
    """Every solid of ``body.assembly`` is in the scene, in the frame that
    puts it where the assembly does in every view (same volume, its centre
    moved by the view's frame transform onto the assembly's), save the plain
    blocks the scene draws in detail (``DETAIL``); those details fill or sit
    in the block they replace."""
    lay = layout(ROUTES[route])
    scene = {n: (s, f) for n, s, f, _m, _c in ES.scene_parts(route)}
    assert len(scene) == len(ES.scene_parts(route)), "scene part names are not unique"
    shut = {n: s for n, s, _ in body.assembly(route, 0.0, False)}
    for view, v in ES.VIEWS.items():
        asm = body.assembly(route, v.lid_deg, v.bank_out)
        assert {n for n, _, _ in asm} == set(shut)
        for name, shape, _colour in asm:
            if name in ES.DETAIL:
                assert name not in scene, name
                continue
            s, frame = scene[name]
            m = ES.frame_matrix(lay, frame, v.lid_deg, v.bank_out)
            assert s.Volume() == pytest.approx(shape.Volume(), rel=1e-6), (view, name)
            c = s.Center()
            assert _apply(m, (c.x, c.y, c.z)) == pytest.approx(
                tuple(shape.Center()), abs=1e-6), (view, name)
    frames = {n: f for n, (_, f) in scene.items()}
    assert frames["bank"] == "bank" and frames["monitor"] == "lid" and frames["board"] == "base"
    assert lay.boost_in_lid and frames["boost"] == "lid"      # R25: taped in the lid strip

    # the details: the TinyVGA's fill its block; the plug's hood sits in the
    # plug + stiff run block, at the adapter's socket end
    tv = [_bb(scene[n][0]) for n in ES.DETAIL["tinyvga"]]
    got = [min(b[i] for b in tv) if i < 3 else max(b[i] for b in tv) for i in range(6)]
    assert got == pytest.approx(_bb(shut["tinyvga"]), abs=1e-3)
    (hood,) = (scene[n][0] for n in ES.DETAIL["vga-plug"])
    h, k = _bb(hood), _bb(shut["vga-plug"])
    assert all(h[i] >= k[i] - 1e-3 for i in range(3)) and all(
        h[i] <= k[i] + 1e-3 for i in range(3, 6))
    assert h[1] == pytest.approx(k[1], abs=1e-3)


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_pigtail_follows_route(route):
    """R4: the monitor's pigtail is drawn along ``checks.pigtail_path`` at the
    view's lid angle: a tube from the exit on the panel's cable edge, through
    the hinge notch and down the plug's stiff run, to the back of the plug
    body; the moulded hood then fills the path's last leg to the plug's face
    in the adapter's socket."""
    lay = layout(ROUTES[route])
    board = body.ASSEMBLY_BOARD
    hood = next(s for n, s, *_ in ES.scene_parts(route) if n in ES.DETAIL["vga-plug"])
    hb = _bb(hood)
    for angle in sorted({v.lid_deg for v in ES.VIEWS.values()}):
        path = pigtail_path(lay, angle, board)
        pts = ES.pigtail_points(lay, angle, board)
        assert pts == [pytest.approx(p) for p in path[:-1]], angle
        r = ES.PIGTAIL_R
        legs = ES.pigtail(lay, angle, board)
        assert legs and all(f == "base" for _, _, f in legs)
        boxes = [_bb(s) for _, s, _ in legs]
        lo = [min(b[i] for b in boxes) for i in range(3)]
        hi = [max(b[i] for b in boxes) for i in range(3, 6)]
        for i in range(3):
            assert lo[i] == pytest.approx(min(p[i] for p in pts) - r, abs=0.05), (angle, i)
            assert hi[i] == pytest.approx(max(p[i] for p in pts) + r, abs=0.05), (angle, i)
        # the hood: from the plug's back to its face, round the path's axis
        back, face = path[-2], path[-1]
        assert (hb[1], hb[4]) == pytest.approx((face[1], back[1]), abs=1e-3)
        assert hb[0] < face[0] < hb[3] and hb[2] < face[2] < hb[5]


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_screen_on_monitor_face(route):
    """The lit test pattern lies on the taped monitor's face (its underside,
    lid shut), over the panel's active area: just proud of the face, inside
    the block in X and Y, the image's bottom at the cable (hinge) edge."""
    lay = layout(ROUTES[route])
    mon = _bb(next(s for n, s, _ in body.assembly(route, 0.0, False) if n == "monitor"))
    q = ES.screen_quad(lay)
    assert len(q) == 4
    for x, y, z in q:
        assert mon[0] < x < mon[3] and mon[1] < y < mon[4]
        assert z == pytest.approx(mon[2] - ES.SCREEN_PROUD)
    (x0, y_lo, _), (x1, _, _), (_, y_hi, _), _ = q
    assert x1 > x0 and y_lo > y_hi       # image bottom towards the hinge (+Y)


def test_test_pattern():
    OUT.mkdir(parents=True, exist_ok=True)
    p = ES.test_pattern(OUT / "pattern-check.png")
    from PIL import Image
    im = Image.open(p)
    assert im.size == ES.PATTERN_SIZE
    assert len(set(im.convert("RGB").get_flattened_data())) > 8   # bars, not a flat fill


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_bought_parts_present(route):
    """The renders sell the idea: the board, its TinyVGA, adapter and plugs,
    the monitor (lit), the boost module, the bank and the cables."""
    names = {n: m for n, _s, _f, m, _c in ES.scene_parts(route)}
    for want in ("board", "monitor", "boost", "bank", "tinyvga-pcb", "tinyvga-de15",
                 "vga-adapter", "vga-plug-hood", "usb-c-plug", "usb-c-cable-0", "pmod-J13",
                 "display-7seg"):
        assert want in names, (route, want)
    assert names["board"] == "pcb"


# --- the manifests (slow: every STL) ------------------------------------------------------

@pytest.fixture(scope="module")
def manifests():
    paths = ES.export(OUT)
    return {n: (p, json.loads(p.read_text())) for n, p in paths.items()}


@pytest.mark.slow
def test_writes_every_manifest(manifests):
    assert set(manifests) == EXPECTED
    for name, (p, _) in manifests.items():
        assert p == OUT / f"{name}.json"


@pytest.mark.slow
def test_every_referenced_file_exists(manifests):
    for name, (p, m) in manifests.items():
        assert m["parts"], name
        for e in m["parts"]:
            f = p.parent / e["file"]
            assert f.is_file() and f.stat().st_size > 84, (name, e["part"], f)
            assert len(e["colour"]) == 3 and all(0.0 <= c <= 1.0 for c in e["colour"])
            assert e["material"] in ES.MATERIALS, (name, e["part"], e["material"])
        for s in m.get("screens", ()):
            assert (p.parent / s["image"]).is_file()
            assert len(s["quad"]) == 4


@pytest.mark.slow
def test_views_place_lid_bank_and_pigtail(manifests):
    lay = layout(ROUTES["printed"])
    lift = lay.rim_z + BANK_OUT_LIFT - lay.bank_bay.z0
    for route in ("printed", "laser"):
        for view, v in ES.VIEWS.items():
            _, m = manifests[f"{route}-{view}"]
            assert (m["lid_deg"], m["bank_out"]) == (v.lid_deg, v.bank_out)
            by = {e["part"]: e for e in m["parts"]}
            for part in ("monitor", "boost"):
                assert _lid_angle(_matrix(by[part])) == pytest.approx(v.lid_deg), part
            assert _matrix(by["board"]) == [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0],
                                            [0, 0, 0, 1]]
            assert _matrix(by["bank"])[2][3] == pytest.approx(lift if v.bank_out else 0.0)
            for s in m["screens"]:
                assert _lid_angle(_matrix(s)) == pytest.approx(v.lid_deg)
            pig = [e for n, e in by.items() if n.startswith("pigtail-")]
            assert pig and all(e["file"].startswith(f"{route}/pigtail-{v.lid_deg:g}deg/")
                               for e in pig), (route, view)
    _, lm = manifests["laser-open-front"]
    lby = {e["part"]: e for e in lm["parts"]}
    assert _lid_angle(_matrix(lby["lid-front"])) == pytest.approx(LID_OPEN_DEG)


@pytest.mark.slow
def test_flatpack_has_every_panel_flat_and_apart(manifests):
    from demobox.laser import panels as P
    lay = layout(ROUTES["laser"])
    pans = P.build(lay, lay.wall, P.KERF)
    _, m = manifests["laser-flatpack"]
    by = {e["part"]: e for e in m["parts"]}
    assert set(by) == set(pans.panels)
    rects = []
    for name, e in by.items():
        t = _matrix(e)
        assert [row[:3] for row in t[:3]] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]], name
        u0, v0, u1, v1 = pans.panels[name].shape.bounds
        x, y = t[0][3], t[1][3]
        rects.append((x, y, x + u1 - u0, y + v1 - v0))
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)
