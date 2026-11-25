"""render/annotate.py: the dimension overlay drawn onto the renders.

Synthetic white PNGs and sidecars (the Task 1 ``<png>.dims.json`` format,
every point in top-left pixels); no Blender.
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from render import annotate as A  # noqa: E402

from tools.drafting.style import C_DIM  # noqa: E402

#: Written under the repo's git-ignored tmp/ (house rule: never /tmp).
OUT = ROOT / "tmp" / "test-annotate"

DIM_RGB = tuple(int(C_DIM[i:i + 2], 16) for i in (1, 3, 5))


def _linear(label, a, b, line_a, line_b, fallback=False):
    return {"label": label, "kind": "linear", "fallback": fallback,
            "a": list(a), "b": list(b), "line_a": list(line_a), "line_b": list(line_b)}


def _write(name: str, size, dims) -> tuple[Path, Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    png = OUT / f"{name}.png"
    Image.new("RGB", size, "white").save(png)
    side = png.with_name(png.name + ".dims.json")
    side.write_text(json.dumps({"resolution": list(size), "dimensions": dims}))
    return png, side


def _sidecar(png: Path) -> dict:
    return json.loads(png.with_name(png.name + ".dims.json").read_text())


def _overlap(p, q) -> bool:
    return p[0] < q[2] and q[0] < p[2] and p[1] < q[3] and q[1] < p[3]


def test_annotate_draws_dim_colour():
    png, side = _write("colour", (800, 600), [
        _linear("300", (100, 400), (500, 400), (100, 450), (500, 450))])
    A.annotate(png, side)
    img = Image.open(png).convert("RGB")
    # the dimension line itself, clear of the label in the middle
    for x in (130, 180, 420, 470):
        assert img.getpixel((x, 450)) == DIM_RGB, x
    # extension lines from the anchors down to the line
    assert img.getpixel((100, 425)) == DIM_RGB
    assert img.getpixel((500, 425)) == DIM_RGB


def test_labels_inside_and_apart():
    w, h = 400, 200
    dims = [_linear("1234.5", (40, 150), (360, 150), (40, 120), (360, 120)),
            # a vertical dimension whose line crosses the first one's middle
            _linear("80", (230, 100), (230, 180), (200, 100), (200, 180)),
            _linear("250", (60, 60), (300, 60), (60, 40), (300, 40))]
    plan = A.plan(_sidecar(_write("inside", (w, h), dims)[0]))
    assert [p.label for p in plan.placed] == ["1234.5", "80", "250"]
    for p in plan.placed:
        x0, y0, x1, y1 = p.box
        assert 0 <= x0 < x1 <= w and 0 <= y0 < y1 <= h, (p.label, p.box)
    for i, p in enumerate(plan.placed):
        for q in plan.placed[i + 1:]:
            assert not _overlap(p.box, q.box), (p.label, q.label)
    # the first label is nudged along its own line, clear of the crossing one
    first = plan.placed[0]
    cx, cy = first.centre
    assert cy == pytest.approx(120, abs=0.5)
    assert not first.box[0] <= 200 <= first.box[2]
    assert 40 < cx < 360


def test_label_longer_than_its_line_raises():
    png, side = _write("short", (400, 200), [
        _linear("1234.5", (100, 100), (150, 100), (100, 120), (150, 120))])
    with pytest.raises(A.PlacementError, match="between its arrowheads"):
        A.annotate(png, side)


def test_point_outside_raises():
    png, side = _write("outside", (400, 300), [
        _linear("100", (10, 10), (410, 10), (10, 30), (390, 30))])
    with pytest.raises(ValueError, match="outside"):
        A.annotate(png, side)


def test_resolution_mismatch_raises():
    png, side = _write("mismatch", (400, 300), [
        _linear("100", (10, 10), (300, 10), (10, 30), (300, 30))])
    side.write_text(json.dumps({**json.loads(side.read_text()), "resolution": [800, 600]}))
    with pytest.raises(ValueError, match="resolution"):
        A.annotate(png, side)


def test_unresolvable_overlap_raises():
    """Same line twice: every place on it covers the other's line."""
    png, side = _write("overlap", (200, 40), [
        _linear("100", (20, 10), (180, 10), (20, 20), (180, 20)),
        _linear("101", (20, 10), (180, 10), (20, 20), (180, 20))])
    with pytest.raises(A.PlacementError, match="covers a line"):
        A.annotate(png, side)


def test_label_overlap_raises():
    """Two parallel lines 28 px apart, nothing crossing: their labels (32 px
    font at h = 1600, so about 29 px tall) cannot be nudged apart along lines
    too short to let them pass each other."""
    w, h = 400, 1600
    # lines at y = 100 and 128; extension lines at x = 100 and 300 only, from
    # y = 60 down to 108 and from y = 170 up to 120: nothing crosses a label
    dims = [_linear("100.00", (100, 60), (300, 60), (100, 100), (300, 100)),
            _linear("101.00", (100, 170), (300, 170), (100, 128), (300, 128))]
    plan_one = A.plan({"resolution": [w, h], "dimensions": dims[1:]})
    assert plan_one.placed                 # alone, the second label fits
    png, side = _write("label-overlap", (w, h), dims)
    with pytest.raises(A.PlacementError, match="overlaps label '100.00'"):
        A.annotate(png, side)


def test_frame_edge_nudges_along_line():
    """A shallow diagonal near the bottom edge: the centred label would clip
    the frame, so it moves along the line, up and inward, staying on it."""
    w, h = 400, 200
    la, lb = (50, 199), (350, 180)
    png, side = _write("edge", (w, h), [_linear("100", (50, 170), (350, 150), la, lb)])
    plan = A.plan(_sidecar(png))
    p = plan.placed[0]
    x0, y0, x1, y1 = p.box
    assert 0 <= x0 and x1 <= w and 0 <= y0 and y1 <= h
    # centred at the middle it would have clipped
    mid = ((la[0] + lb[0]) / 2, (la[1] + lb[1]) / 2)
    assert mid[1] + (y1 - y0) / 2 > h - A.GAP
    cx, cy = p.centre
    # still on its line, nudged towards line_b (inward)
    t = (cx - la[0]) / (lb[0] - la[0])
    assert cy == pytest.approx(la[1] + t * (lb[1] - la[1]), abs=0.5)
    assert cx > mid[0]


def test_outline_drawn_without_label():
    pts = [[100, 100], [300, 100], [300, 250], [100, 250], [100, 100]]
    dims = [{"kind": "outline", "style": "line", "fallback": False, "points": pts},
            _linear("200", (100, 250), (300, 250), (100, 290), (300, 290))]
    png, side = _write("outline", (400, 320), dims)
    plan = A.plan(_sidecar(png))
    assert [p.label for p in plan.placed] == ["200"]
    assert plan.dims[0]["kind"] == "outline"
    A.annotate(png, side)
    img = Image.open(png).convert("RGB")
    for xy in ((200, 100), (300, 175), (100, 175)):
        assert img.getpixel(xy) == DIM_RGB, xy


def test_outline_point_outside_raises():
    png, side = _write("outline-out", (400, 300), [
        {"kind": "outline", "style": "line", "fallback": False,
         "points": [[10, 10], [500, 10]]}])
    with pytest.raises(ValueError, match="outside"):
        A.annotate(png, side)


def test_missing_key_raises():
    d = _linear("100", (10, 10), (300, 10), (10, 30), (300, 30))
    del d["fallback"]
    png, side = _write("nokey", (400, 300), [d])
    with pytest.raises(ValueError, match="fallback"):
        A.annotate(png, side)


def _crowded(fallbacks: bool):
    """Ten panels' dimensions piled on one short spot, plus (if ``fallbacks``)
    the kit's X and Y extents well clear of them."""
    dims = [_linear(f"{100 + i}", (300, 300), (330, 300), (300, 310), (330, 310))
            for i in range(10)]
    if fallbacks:
        dims += [_linear("700", (100, 100), (700, 100), (100, 540), (700, 540), True),
                 _linear("500", (100, 100), (100, 500), (40, 100), (40, 500), True)]
    return dims


def test_flatpack_falls_back_when_crowded():
    png, side = _write("crowded", (800, 600), _crowded(True))
    plan = A.plan(_sidecar(png))
    assert plan.fallback
    assert [p.label for p in plan.placed] == ["700", "500"]        # both extents (P2b)
    A.annotate(png, side)
    img = Image.open(png).convert("RGB")
    assert img.getpixel((150, 540)) == DIM_RGB                       # the X extent's line
    # without the fallback entries in the sidecar, crowding is an error
    png2, side2 = _write("crowded-nofb", (800, 600), _crowded(False))
    with pytest.raises(A.PlacementError):
        A.annotate(png2, side2)


def test_fallback_not_drawn_when_panels_fit():
    dims = [_linear("300", (100, 300), (400, 300), (100, 330), (400, 330)),
            _linear("700", (100, 100), (700, 100), (100, 540), (700, 540), True)]
    plan = A.plan(_sidecar(_write("fits", (800, 600), dims)[0]))
    assert not plan.fallback
    assert [p.label for p in plan.placed] == ["300"]


def test_angle_drawn_along_arc():
    c = (400, 300)
    arc = [[c[0] + 150 * math.cos(math.radians(-90 + 100 * i / 32)),
            c[1] + 150 * math.sin(math.radians(-90 + 100 * i / 32))] for i in range(33)]
    dims = [{"label": "100\N{DEGREE SIGN}", "kind": "angle", "fallback": False,
             "centre": list(c), "a": arc[0], "b": arc[-1], "arc": arc}]
    png, side = _write("angle", (800, 600), dims)
    plan = A.plan(_sidecar(png))
    box = plan.placed[0].box
    mid = arc[16]
    assert box[0] <= mid[0] <= box[2] and box[1] <= mid[1] <= box[3]
    A.annotate(png, side)
    img = Image.open(png).convert("RGB")
    near = [img.getpixel((round(p[0]), round(p[1]))) for p in arc[3:6]]
    assert DIM_RGB in near


def test_deterministic():
    dims = [_linear("300", (100, 400), (500, 400), (100, 450), (500, 450)),
            _linear("200", (100, 100), (100, 400), (60, 100), (60, 400))]
    p1, s1 = _write("det1", (800, 600), dims)
    p2, s2 = _write("det2", (800, 600), dims)
    A.annotate(p1, s1)
    A.annotate(p2, s2)
    assert p1.read_bytes() == p2.read_bytes()


def test_missing_sidecar_fails_cli():
    png, side = _write("nosidecar", (200, 100), [])
    side.unlink()
    r = subprocess.run([sys.executable, str(ROOT / "render" / "annotate.py"), str(png)],
                       capture_output=True, text=True)
    assert r.returncode != 0
    assert "dims.json" in r.stderr


def test_annotate_runs_without_bpy():
    code = ("import sys; sys.path.insert(0, %r); import render.annotate; "
            "assert 'bpy' not in sys.modules, 'bpy imported'" % str(ROOT))
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_extension_line_gap():
    """P8: every extension line starts EXT_GAP (5 px) off its anchor."""
    assert A.EXT_GAP == 5
    png, side = _write("gap", (800, 600), [
        _linear("300", (100, 400), (500, 400), (100, 450), (500, 450))])
    A.annotate(png, side)
    img = Image.open(png).convert("RGB")
    for x in (100, 500):
        for y in range(398, 405):                      # the gap below the anchor
            assert img.getpixel((x, y)) == (255, 255, 255), (x, y)
        assert img.getpixel((x, 407)) == DIM_RGB       # then the line
    # the segment itself starts EXT_GAP along, towards the line
    assert A._segments(_linear("1", (0, 0), (0, 100), (50, 0), (50, 100)), 200, 200)[1][0] \
        == pytest.approx((5.0, 0.0))


def test_area_outline_heavy_and_tinted():
    """P8: an "area" outline is drawn at the dimension line's width with a
    light translucent C_DIM fill; a "line" outline is thin and unfilled."""
    pts = [[100, 100], [300, 100], [300, 250], [100, 250], [100, 100]]
    png, side = _write("area", (400, 320), [
        {"kind": "outline", "style": "area", "fallback": False, "points": pts}])
    A.annotate(png, side)
    img = Image.open(png).convert("RGB")
    inside = img.getpixel((200, 175))
    assert inside not in ((255, 255, 255), DIM_RGB)
    # a tint of C_DIM over white, at ALPHA
    want = tuple(round(255 + (c - 255) * A.AREA_ALPHA) for c in DIM_RGB)
    assert all(abs(a - b) <= 1 for a, b in zip(inside, want)), (inside, want)
    assert 0.15 <= A.AREA_ALPHA <= 0.20
    assert img.getpixel((50, 50)) == (255, 255, 255)
    lw = max(2, 320 // 400)
    heavy = sum(img.getpixel((200, y)) == DIM_RGB for y in range(95, 106))
    assert heavy >= lw
    png2, side2 = _write("thin", (400, 320), [
        {"kind": "outline", "style": "line", "fallback": False, "points": pts}])
    A.annotate(png2, side2)
    img2 = Image.open(png2).convert("RGB")
    assert img2.getpixel((200, 175)) == (255, 255, 255)


def test_outline_unknown_style_raises():
    png, side = _write("badstyle", (400, 300), [
        {"kind": "outline", "style": "dotted", "fallback": False,
         "points": [[10, 10], [200, 10]]}])
    with pytest.raises(ValueError, match="style"):
        A.annotate(png, side)


# --- P9: labels follow their line ----------------------------------------------------

def test_label_rotated_to_slanted_line():
    dims = [_linear("300", (100, 330), (400, 180), (100, 300), (400, 150))]
    plan = A.plan(_sidecar(_write("slant", (500, 400), dims)[0]))
    want = math.degrees(math.atan2(150, 300))           # rising to the right: +26.6
    assert plan.placed[0].angle == pytest.approx(want, abs=1.0)


def test_label_never_upside_down():
    """A line drawn right to left reads the same as left to right; angles
    stay in (-90, 90]."""
    ltr = [_linear("300", (100, 330), (400, 180), (100, 300), (400, 150))]
    rtl = [_linear("300", (400, 180), (100, 330), (400, 150), (100, 300))]
    a = A.plan(_sidecar(_write("ltr", (500, 400), ltr)[0])).placed[0].angle
    b = A.plan(_sidecar(_write("rtl", (500, 400), rtl)[0])).placed[0].angle
    assert a == pytest.approx(b, abs=1e-6)
    up = [_linear("300", (130, 350), (130, 50), (100, 350), (100, 50))]
    down = [_linear("300", (130, 50), (130, 350), (100, 50), (100, 350))]
    for d in (up, down):
        assert A.plan(_sidecar(_write("vert", (400, 400), d)[0])).placed[0].angle \
            == pytest.approx(90.0)


def test_rotated_label_fits_where_upright_box_would_clip():
    """A vertical line 15 px from the left edge: an upright label box would
    run off the frame; turned along the line it fits."""
    w, h = 400, 400
    png, side = _write("rot-frame", (w, h), [
        _linear("123.45", (40, 20), (40, 380), (15, 20), (15, 380))])
    plan = A.plan(_sidecar(png))
    p = plan.placed[0]
    assert p.angle == pytest.approx(90.0)
    assert p.centre[0] == pytest.approx(15, abs=0.5)
    for x, y in p.poly:
        assert A.GAP <= x <= w - A.GAP and A.GAP <= y <= h - A.GAP
    upright_w = p.size[0]                                # the label's length along its line
    assert 15 - upright_w / 2 < 0                        # upright, it would have clipped
    A.annotate(png, side)


def test_rotated_labels_overlap_by_shape_not_bounding_box():
    """Two parallel 45-degree lines 40 px apart: their labels' bounding boxes
    overlap but the turned labels do not, so both stay at their middles."""
    r2 = math.sqrt(2)
    n = (1 / r2, -1 / r2)

    def sh(p, k):
        return (p[0] + n[0] * k, p[1] + n[1] * k)
    l1 = ((100, 100), (300, 300))
    l2 = (sh(l1[0], 40), sh(l1[1], 40))
    dims = [_linear("150.0", sh(l1[0], -30), sh(l1[1], -30), *l1),
            _linear("151.0", sh(l2[0], 30), sh(l2[1], 30), *l2)]
    plan = A.plan(_sidecar(_write("rot-overlap", (400, 400), dims)[0]))
    p, q = plan.placed
    assert p.angle == pytest.approx(-45.0) and q.angle == pytest.approx(-45.0)
    assert p.centre == pytest.approx((200, 200), abs=0.5)
    assert q.centre == pytest.approx(sh((200, 200), 40), abs=0.5)
    assert _overlap(p.box, q.box)                        # the bounding boxes do
