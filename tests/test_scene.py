"""scripts/export_scene.py: the Blender scene manifests (Task 9).

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

from demobox.layout import LID_OPEN_DEG, ROUTES, layout  # noqa: E402

#: Written under the repo's git-ignored tmp/ (house rule: never /tmp).
OUT = ROOT / "tmp" / "test-scene"

EXPECTED = {f"{r}-{v}" for r in ("printed", "laser")
            for v in ("closed", "open-front", "open-back", "drawer-out")} | {"laser-flatpack"}


def _matrix(entry) -> list[list[float]]:
    t = entry["transform"]
    assert len(t) == 16
    return [t[0:4], t[4:8], t[8:12], t[12:16]]


def _lid_angle(m) -> float:
    """Opening angle (degrees) of a lid-frame transform: the lid turns by
    -angle about +X (``Layout.lid_location``)."""
    assert abs(m[0][0] - 1.0) < 1e-9 and abs(m[1][0]) < 1e-9 and abs(m[2][0]) < 1e-9
    return -math.degrees(math.atan2(m[2][1], m[1][1]))


def test_render_names():
    assert set(ES.RENDERS) == EXPECTED


def test_makefile_renders_match():
    """``make renders`` loops over the Makefile's RENDERS: the same list."""
    text = (ROOT / "Makefile").read_text().replace("\\\n", " ")
    line = next(ln for ln in text.splitlines() if ln.startswith("RENDERS :="))
    assert line.split(":=", 1)[1].split() == list(ES.RENDERS)


def test_round_head():
    import cadquery as cq
    box = cq.Solid.makeBox(5.5, 3.0, 5.5, cq.Vector(10, 20, 30))
    s = ES._round_head(box)
    c = s.BoundingBox()
    assert (c.xmin, c.ymin, c.zmin, c.xmax, c.ymax, c.zmax) == pytest.approx(
        (10, 20, 30, 15.5, 23, 35.5), abs=1e-6)
    assert s.Volume() == pytest.approx(math.pi * 2.75 ** 2 * 3.0)


def test_lid_transform_matches_layout():
    lay = layout(ROUTES["printed"])
    m = ES.frame_matrix(lay, "lid", LID_OPEN_DEG, 0.0)
    assert _lid_angle([m[0:4], m[4:8], m[8:12], m[12:16]]) == pytest.approx(LID_OPEN_DEG)
    # The STLs hold the lid parts shut, in the base frame, so the transform
    # is the turn about the hinge axis: the axis stays put, and a shut lid
    # point (lid frame (y, z) + the axis) lands where Layout._open_yz (the
    # profile the fit checks use) puts it.
    hy, hz = lay.hinge_axis
    assert (m[3], m[5] * hy + m[6] * hz + m[7], m[9] * hy + m[10] * hz + m[11]) == \
        pytest.approx((0.0, hy, hz))
    y, z = -150.0, 20.0
    Y, Z = hy + y, hz + z
    assert (m[5] * Y + m[6] * Z + m[7], m[9] * Y + m[10] * Z + m[11]) == pytest.approx(
        lay._open_yz(y, z, LID_OPEN_DEG))
    assert ES.frame_matrix(lay, "lid", 0.0, 0.0) == pytest.approx(ES.IDENTITY)
    d = ES.frame_matrix(lay, "drawer", 0.0, 50.0)
    assert d[3] == pytest.approx(-50.0) and d[7] == pytest.approx(0.0)
    assert ES.frame_matrix(lay, "base", LID_OPEN_DEG, 50.0) == pytest.approx(
        [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])


def test_test_pattern():
    OUT.mkdir(parents=True, exist_ok=True)
    p = ES.test_pattern(OUT / "pattern-check.png")
    from PIL import Image
    im = Image.open(p)
    assert im.size == ES.PATTERN_SIZE
    assert len(set(im.convert("RGB").get_flattened_data())) > 8   # bars, not a flat fill


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
def test_open_front_lid_at_open_angle(manifests):
    _, m = manifests["printed-open-front"]
    assert m["lid_deg"] == LID_OPEN_DEG
    by = {e["part"]: e for e in m["parts"]}
    for part in ("lid", "bezel", "panel", "hinge-lid"):
        assert _lid_angle(_matrix(by[part])) == pytest.approx(LID_OPEN_DEG), part
    for part in ("base", "deck", "board"):
        assert _matrix(by[part]) == [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
    for s in m["screens"]:
        assert _lid_angle(_matrix(s)) == pytest.approx(LID_OPEN_DEG)
    _, lm = manifests["laser-open-front"]
    lby = {e["part"]: e for e in lm["parts"]}
    assert _lid_angle(_matrix(lby["lid-front"])) == pytest.approx(LID_OPEN_DEG)


@pytest.mark.slow
def test_closed_and_drawer_out(manifests):
    lay = layout(ROUTES["printed"])
    _, closed = manifests["printed-closed"]
    by = {e["part"]: e for e in closed["parts"]}
    assert _lid_angle(_matrix(by["lid"])) == pytest.approx(0.0)
    _, out = manifests["printed-drawer-out"]
    by = {e["part"]: e for e in out["parts"]}
    assert _matrix(by["drawer"])[0][3] == pytest.approx(-lay.drawer_travel)
    assert _matrix(by["bank"])[0][3] == pytest.approx(-lay.drawer_travel)
    assert _matrix(by["base"])[0][3] == pytest.approx(0.0)


@pytest.mark.slow
def test_bought_parts_present(manifests):
    """The renders sell the idea: the board, its TinyVGA and plugs, the
    monitor and its lit screen, the bank."""
    for route in ("printed", "laser"):
        _, m = manifests[f"{route}-open-front"]
        names = {e["part"] for e in m["parts"]}
        for want in ("board", "panel", "bank", "tinyvga-pcb", "tinyvga-de15", "vga-plug",
                     "usb-c-plug", "pmod-J13"):
            assert want in names, (route, want)
        assert {e["material"] for e in m["parts"] if e["part"] == "board"} == {"pcb"}
        assert len(m["screens"]) == 1


@pytest.mark.slow
def test_flatpack_has_every_panel_flat_and_apart(manifests):
    from demobox.laser import panels as P
    lay = layout(ROUTES["laser"])
    body = P.build(lay, lay.wall, P.KERF)
    _, m = manifests["laser-flatpack"]
    by = {e["part"]: e for e in m["parts"]}
    assert set(by) == set(body.panels)
    rects = []
    for name, e in by.items():
        t = _matrix(e)
        assert [row[:3] for row in t[:3]] == [[1, 0, 0], [0, 1, 0], [0, 0, 1]], name
        u0, v0, u1, v1 = body.panels[name].shape.bounds
        x, y = t[0][3], t[1][3]
        rects.append((x, y, x + u1 - u0, y + v1 - v0))
    for i, a in enumerate(rects):
        for b in rects[i + 1:]:
            assert a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1], (a, b)
