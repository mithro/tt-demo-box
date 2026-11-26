"""The committed renders in output/renders/ agree with the layout (review I2).

``make check`` does not rebuild the renders (Cycles noise), so these fast
tests (no Blender) read each committed sidecar ``<png>.dims.json`` and PNG
and check they still say what ``export_scene.view_dimensions`` says now: a
layout change that is not followed by ``make renders`` fails here instead of
leaving old numbers burned into the images.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import export_scene as ES  # noqa: E402

from demobox.layout import LID_OPEN_DEG, ROUTES, layout  # noqa: E402
from render import annotate as A  # noqa: E402

RENDERS = ROOT / "output" / "renders"
REMEDY = "the committed render is stale: run `make renders` and commit output/renders/"
#: How far the open-back arc's arms may be from LID_OPEN_DEG on screen (I1).
ARC_TOLERANCE_DEG = 25.0


def _route_view(name: str) -> tuple[str, str]:
    route, view = name.split("-", 1)
    return route, view


def _files(name: str) -> tuple[Path, Path]:
    png = RENDERS / f"{name}.png"
    side = A.sidecar_for(png)
    assert png.is_file(), f"{png} is missing; {REMEDY}"
    assert side.is_file(), f"{side} is missing; {REMEDY}"
    return png, side


def _key(d: dict) -> tuple:
    return d["kind"], d.get("label"), d["fallback"]


@pytest.mark.parametrize("name", ES.RENDERS)
def test_committed_render_matches_layout(name):
    """Each committed sidecar's entries (kind, label, ``fallback``), in
    order, are ``view_dimensions``' for its route and view; its resolution
    is the render's; the PNG is that size and annotated; and annotate can
    plan its labels on it."""
    png, side_path = _files(name)
    side = json.loads(side_path.read_text())
    route, view = _route_view(name)
    want = [_key(d) for d in ES.view_dimensions(layout(ROUTES[route]), route, view)]
    got = [_key(d) for d in side["dimensions"]]
    assert got == want, f"{name}: sidecar dimensions {got}, layout says {want}; {REMEDY}"
    assert side["resolution"] == list(ES.RESOLUTION), \
        f"{name}: sidecar resolution {side['resolution']}, renders are {ES.RESOLUTION}; {REMEDY}"
    img = Image.open(png)
    assert img.size == tuple(ES.RESOLUTION), f"{name}: PNG is {img.size}; {REMEDY}"
    assert img.text.get(A.MARKER[0]) == A.MARKER[1], \
        f"{name}: PNG has no dimension overlay (no {A.MARKER[0]!r} chunk); {REMEDY}"
    try:
        A.plan(side, img.size)
    except ValueError as e:
        pytest.fail(f"{name}: annotate cannot plan its labels: {e}; {REMEDY}")


def test_every_committed_render_is_known():
    """No stray render or sidecar in output/renders/ outside ``RENDERS``."""
    names = {p.name.split(".png")[0] for p in RENDERS.iterdir()}
    assert names == set(ES.RENDERS), f"output/renders/ has {sorted(names)}; {REMEDY}"


def _screen_angle(d: dict) -> float:
    c, a, b = d["centre"], d["a"], d["b"]
    va, vb = (a[0] - c[0], a[1] - c[1]), (b[0] - c[0], b[1] - c[1])
    cos = (va[0] * vb[0] + va[1] * vb[1]) / math.hypot(*va) / math.hypot(*vb)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_open_back_arc_reads_as_its_angle(route):
    """I1: on open-back the lid-angle arc's arms, as projected, are within
    ARC_TOLERANCE_DEG of LID_OPEN_DEG, so the arc reads as that angle (on
    open-front's right face it read as about 160 degrees)."""
    _png, side_path = _files(f"{route}-open-back")
    angles = [d for d in json.loads(side_path.read_text())["dimensions"] if d["kind"] == "angle"]
    assert len(angles) == 1, f"{route}-open-back: {len(angles)} angle entries, want 1; {REMEDY}"
    (d,) = angles
    got = _screen_angle(d)
    assert abs(got - LID_OPEN_DEG) <= ARC_TOLERANCE_DEG, \
        f"{route}-open-back: the arc's arms are {got:.1f} deg apart on screen, " \
        f"want {LID_OPEN_DEG:g} +- {ARC_TOLERANCE_DEG:g}"
