"""render/annotate.py: the dimension overlay drawn onto the renders.

Synthetic white PNGs and sidecars (the Task 1 ``<png>.dims.json`` format,
every point in top-left pixels); no Blender.
"""

from __future__ import annotations

import json
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
    with pytest.raises(A.PlacementError, match="between the arrowheads"):
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
    png, side = _write("overlap", (200, 40), [
        _linear("100", (20, 10), (180, 10), (20, 20), (180, 20)),
        _linear("101", (20, 10), (180, 10), (20, 20), (180, 20))])
    with pytest.raises(A.PlacementError):
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
    import math
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
