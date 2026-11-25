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

from demobox import geom  # noqa: E402
from demobox.checks import pigtail_path  # noqa: E402
from demobox.parts.batteries import BATTERIES  # noqa: E402
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


# --- dimensions ---------------------------------------------------------------------
#
# The manifests are in mm: the parts' ``transform``s are mm (``frame_matrix``)
# and the dimension anchors are in the same frame and units, so a scene-unit
# distance is already mm (ruling P1: convert before comparing; the factor is 1).

SCENE_UNIT_MM = 1.0
DEG = "\N{DEGREE SIGN}"


def _dist_mm(e) -> float:
    return math.dist(e["a"], e["b"]) * SCENE_UNIT_MM


def _labels(dims) -> list[str]:
    return [d["label"] for d in dims]


def _open_extent(lay):
    """The open lid's top (Z) and back (Y), from the layout's own profile."""
    _y0, _z0, y1, z1 = lay.lid_profile_yz(LID_OPEN_DEG).bounds
    return z1, y1


def _expected_labels(lay, view) -> list[str]:
    o, lo, bay = lay.outer, lay.lid_outer, lay.bank_bay
    top, back = _open_extent(lay)
    return {"closed": [geom.mm(o.size[0]), geom.mm(o.size[1]), geom.mm(o.size[2] + lo.size[2])],
            "open-front": [geom.mm(o.size[0]), geom.mm(top), f"{LID_OPEN_DEG:g}{DEG}"],
            "open-back": [geom.mm(o.size[1]), geom.mm(back - o.y1)],
            "bank-out": [geom.mm(bay.size[0]), geom.mm(bay.size[1])]}[view]


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_view_dimensions_per_view(route):
    """The spec's table: closed W, D, H; open-front W, the open height and
    the lid's angle; open-back D and the reach behind the back face;
    bank-out the bay's L and W."""
    lay = layout(ROUTES[route])
    for view in ES.VIEWS:
        dims = ES.view_dimensions(lay, route, view)
        assert _labels(dims) == _expected_labels(lay, view), (route, view)
        for d in dims:
            assert d["fallback"] is False
            if d["kind"] == "linear":
                assert set(d) == {"label", "kind", "a", "b", "offset", "fallback"}
                # the line stands DIM_OFFSET out, square to the measured span
                off = d["offset"]
                assert math.hypot(*off) == pytest.approx(ES.DIM_OFFSET)
                ab = [q - p for p, q in zip(d["a"], d["b"])]
                assert sum(u * v for u, v in zip(ab, off)) == pytest.approx(0.0, abs=1e-9)
            else:
                assert d["kind"] == "angle"
                assert set(d) == {"label", "kind", "centre", "a", "b", "fallback"}
                c = d["centre"]
                ca = [p - q for p, q in zip(d["a"], c)]
                cb = [p - q for p, q in zip(d["b"], c)]
                assert math.hypot(*ca) == pytest.approx(math.hypot(*cb))
                cos = sum(u * v for u, v in zip(ca, cb)) / math.hypot(*ca) / math.hypot(*cb)
                assert math.degrees(math.acos(cos)) == pytest.approx(LID_OPEN_DEG)
                # on the hinge axis, the arms swept by the lid's own transform
                assert c[1:] == pytest.approx(list(lay.hinge_axis))
                m = ES.frame_matrix(lay, "lid", LID_OPEN_DEG, False)
                assert list(_apply(m, d["a"])) == pytest.approx(d["b"])


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_labels_use_geom_mm(route):
    """Every linear label is ``geom.mm`` of its anchors' span (in mm) and
    the layout's value: the same text as the sheets."""
    lay = layout(ROUTES[route])
    for view in ES.VIEWS:
        for d in ES.view_dimensions(lay, route, view):
            if d["kind"] == "linear":
                assert d["label"] == geom.mm(_dist_mm(d)), (route, view, d)
    closed = ES.view_dimensions(lay, route, "closed")
    assert closed[0]["label"] == geom.mm(lay.outer.size[0])
    assert closed[1]["label"] == geom.mm(lay.outer.size[1])


@pytest.mark.parametrize("route", ["printed", "laser"])
def test_open_dimensions_match_assembly(route):
    """The open height and reach (from the layout's lid profile) are what the
    GA sheet measures off the open lid's solids: the top of every part the
    lid moves, and how far behind the back face they go."""
    lay = layout(ROUTES[route])
    still = {n: s.Center() for n, s, _ in body.assembly(route, 0.0, False)}
    moved = [_bb(s) for n, s, _ in body.assembly(route, LID_OPEN_DEG, False)
             if (s.Center() - still[n]).Length > 1e-6]
    top = max(b[5] for b in moved)
    back = max(b[4] for b in moved)
    front = ES.view_dimensions(lay, route, "open-front")
    behind = ES.view_dimensions(lay, route, "open-back")
    assert front[1]["label"] == geom.mm(top)
    assert behind[1]["label"] == geom.mm(back - lay.outer.y1)
    # the open height's top anchor is on the open lid's top
    assert front[1]["b"][2] == pytest.approx(top, abs=1e-6)


@pytest.mark.parametrize("bank", sorted(BATTERIES))
def test_dims_follow_layout(bank):
    """The bank-out dimensions are the bay laid out for that bank."""
    for route, w in ROUTES.items():
        lay = layout(w, bank=bank)
        dims = ES.view_dimensions(lay, route, "bank-out")
        assert _labels(dims) == [geom.mm(lay.bank_bay.size[0]), geom.mm(lay.bank_bay.size[1])]
        for d in dims:
            assert d["label"] == geom.mm(_dist_mm(d))
            assert d["a"][2] == pytest.approx(lay.bank_bay.z1)


def test_flatpack_dimensions():
    """Each panel's (u, v) size, at its place in the kit, plus one
    overall-extent entry (ruling P2: ``fallback``) spanning the kit in X."""
    from demobox.laser import panels as P
    lay = layout(ROUTES["laser"])
    pans = P.build(lay, lay.wall, P.KERF).panels
    dims = ES.view_dimensions(lay, "laser", "flatpack")
    per = [d for d in dims if not d["fallback"]]
    (overall,) = [d for d in dims if d["fallback"]]
    assert len(per) == 2 * len(pans)
    want = sorted(geom.mm(v) for p in pans.values()
                  for v in (p.shape.bounds[2] - p.shape.bounds[0],
                            p.shape.bounds[3] - p.shape.bounds[1]))
    assert sorted(_labels(per)) == want
    place = ES.flatpack_placement(lay)
    x1 = max(x + w for x, _y, w, _h, _t in place.values())
    assert overall["label"] == geom.mm(x1)
    for d in dims:
        assert d["kind"] == "linear" and d["label"] == geom.mm(_dist_mm(d))


def test_manifest_has_dimensions():
    """Every view's manifest and the flat-pack's carry their dimensions."""
    for route in ROUTES:
        lay = layout(ROUTES[route])
        for view in ES.VIEWS:
            m = ES.view_manifest(route, view, [], [], "pattern.png")
            assert m["dimensions"], (route, view)
            assert m["dimensions"] == ES.view_dimensions(lay, route, view)
            json.dumps(m)
    m = ES.flatpack(OUT)
    assert m["dimensions"] == ES.view_dimensions(layout(ROUTES["laser"]), "laser", "flatpack")
    assert any(d["fallback"] for d in m["dimensions"])


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
