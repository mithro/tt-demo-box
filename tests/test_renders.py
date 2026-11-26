"""The committed renders in output/renders/ agree with the layout (review I2, N2).

``make check`` does not rebuild the renders (Cycles noise), so these fast
tests (no Blender) read each committed sidecar ``<png>.dims.json`` and PNG
and check they still say what the code says now: a layout or camera change
that is not followed by ``make renders`` fails here instead of leaving old
numbers, or old positions, burned into the images.

The sidecar's ``projection`` (``render/render_scene.py``) makes it
self-checking: it records each dimension's world points and the camera that
projected them, and ``render_scene`` checked on the render that
``dim_px.camera_view`` reproduces Blender's pixels.  Here:

* the world points are ``view_dimensions``' now (``dim_px.dim_points``);
* reprojecting them with the recorded camera gives the recorded pixels;
* the recorded camera is the one ``dim_px.fit_camera`` chooses now, from
  the view's bearing, the lens, the dimensions' points and the recorded
  parts' bounding-box corners (``fit_parts``); that those corners are the
  scene's parts now needs every STL, so it is a slow test
  (``test_fit_parts_match_the_scene``).
"""

from __future__ import annotations

import copy
import json
import math
import struct
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "render"))
sys.path.insert(0, str(ROOT))

import dim_px as DP  # noqa: E402
import export_scene as ES  # noqa: E402

from demobox.layout import LID_OPEN_DEG, ROUTES, layout  # noqa: E402
from render import annotate as A  # noqa: E402

RENDERS = ROOT / "output" / "renders"
REMEDY = "the committed render is stale: run `make renders` and commit output/renders/"
MM = 0.001
#: How far the open-back arc's arms may be from LID_OPEN_DEG on screen (I1).
ARC_TOLERANCE_DEG = 25.0
#: How far (px) a drawn arc point may be from where it should be on screen:
#: the arms' ends (``a``, ``b``) and a reprojection (``to_px`` rounds to
#: 0.001 px; Blender's float32 maths adds about 0.0001 px).
PX_TOLERANCE = 0.01
#: Each drawn arc point's distance from the centre, as a fraction of the
#: shorter and the longer arm: a circle seen obliquely and in perspective is
#: an ellipse whose radii lie near its arms' (the committed open-back arcs
#: reach 1.00..1.09 of the longer arm).
ARC_RADIUS_RANGE = (0.8, 1.25)
#: World points (mm) and the camera's matrix (m) agree to this.
WORLD_TOLERANCE_MM = 1e-6
CAMERA_TOLERANCE_M = 1e-5
#: The parts' recorded bounding-box corners (m; Blender's float32 maths)
#: agree with the exported scene's to this.
CORNER_TOLERANCE_M = 1e-6


def _route_view(name: str) -> tuple[str, str]:
    route, view = name.split("-", 1)
    return route, view


def _files(name: str) -> tuple[Path, Path]:
    png = RENDERS / f"{name}.png"
    side = A.sidecar_for(png)
    assert png.is_file(), f"{png} is missing; {REMEDY}"
    assert side.is_file(), f"{side} is missing; {REMEDY}"
    return png, side


def _sidecar(name: str) -> dict:
    return json.loads(_files(name)[1].read_text())


def _key(d: dict) -> tuple:
    return d["kind"], d.get("label"), d["fallback"]


def _camera_inputs(view: str) -> dict:
    """What ``render_scene._camera`` is given for ``view`` now."""
    az, el = (ES.FLATPACK_VIEW if view == "flatpack"
              else (ES.VIEWS[view].azimuth_deg, ES.VIEWS[view].elevation_deg))
    return {"azimuth_deg": az, "elevation_deg": el, "lens_mm": ES.LENS_MM,
            "frame_margin": DP.FRAME_MARGIN, "fit_resolution": list(ES.RESOLUTION),
            "sensor_width_mm": DP.SENSOR_WIDTH_MM, "sensor_fit": "HORIZONTAL",
            "shift": [0.0, 0.0], "resolution": list(ES.RESOLUTION)}


def _close(p, q, tol: float) -> bool:
    return len(p) == len(q) and all(abs(a - b) <= tol for a, b in zip(p, q))


def check_render(name: str) -> None:
    """Raise AssertionError (naming ``make renders``) unless the committed
    render ``name`` and its sidecar are what the code makes now."""
    png, side_path = _files(name)
    side = json.loads(side_path.read_text())
    route, view = _route_view(name)
    dims = ES.view_dimensions(layout(ROUTES[route]), route, view)

    # labels, in order
    want = [_key(d) for d in dims]
    got = [_key(d) for d in side["dimensions"]]
    assert got == want, f"{name}: sidecar dimensions {got}, layout says {want}; {REMEDY}"
    assert side["resolution"] == list(ES.RESOLUTION), \
        f"{name}: sidecar resolution {side['resolution']}, renders are {ES.RESOLUTION}; {REMEDY}"
    assert "projection" in side, f"{name}: sidecar has no projection record; {REMEDY}"
    proj = side["projection"]
    cam = proj["camera"]

    # N2: the world points are view_dimensions' now
    world = proj["world_mm"]
    assert len(world) == len(dims), \
        f"{name}: {len(world)} recorded dimensions' world points, want {len(dims)}; {REMEDY}"
    for i, (d, rec) in enumerate(zip(dims, world)):
        now = DP.dim_points(d)
        assert set(rec) == set(now), \
            f"{name}: dimension #{i} world keys {sorted(rec)}, want {sorted(now)}; {REMEDY}"
        for k, v in now.items():
            pts_now, pts_rec = (v, rec[k]) if isinstance(v, list) else ([v], [rec[k]])
            assert len(pts_now) == len(pts_rec) and all(
                _close(p, q, WORLD_TOLERANCE_MM) for p, q in zip(pts_now, pts_rec)), \
                f"{name}: dimension #{i} ({d.get('label', d['kind'])}) {k} was rendered " \
                f"at {pts_rec}, the layout puts it at {[list(p) for p in pts_now]}; {REMEDY}"

    # N2: the camera's inputs are the code's now ...
    for k, v in _camera_inputs(view).items():
        assert (cam[k] == v if isinstance(v, str) else cam[k] == pytest.approx(v)), \
            f"{name}: rendered with camera {k} = {cam[k]}, the code says {v}; {REMEDY}"
    # ... and it is the camera dim_px.fit_camera chooses from them
    corners = [tuple(p) for e in proj["fit_parts"] for p in e["corners_m"]]
    extra = [tuple(v * MM for v in p) for p in DP.flat_points(dims)]
    fitted = DP.fit_camera(cam["azimuth_deg"], cam["elevation_deg"], cam["lens_mm"],
                           cam["fit_resolution"], corners, extra, cam["frame_margin"],
                           cam["sensor_width_mm"])
    assert _close(cam["matrix_world_m"], fitted, CAMERA_TOLERANCE_M), \
        f"{name}: the recorded camera {cam['matrix_world_m']} is not the fitted " \
        f"{fitted}; {REMEDY}"

    # N2: the recorded camera reprojects the world points to the recorded pixels
    for i, (d, rec) in enumerate(zip(side["dimensions"], world)):
        for k, v in rec.items():
            pts_w, pts_px = (v, d[k]) if isinstance(v[0], list) else ([v], [d[k]])
            for p, q in zip(pts_w, pts_px, strict=True):
                again = DP.project_px(cam, tuple(c * MM for c in p), f"{name} #{i} {k}")
                assert _close(again, q, PX_TOLERANCE), \
                    f"{name}: dimension #{i} {k} {p} reprojects to {again}, the sidecar " \
                    f"says {q}; {REMEDY}"

    img = Image.open(png)
    assert img.size == tuple(ES.RESOLUTION), f"{name}: PNG is {img.size}; {REMEDY}"
    assert img.text.get(A.MARKER[0]) == A.MARKER[1], \
        f"{name}: PNG has no dimension overlay (no {A.MARKER[0]!r} chunk); {REMEDY}"
    try:
        A.plan(side, img.size)
    except ValueError as e:
        raise AssertionError(f"{name}: annotate cannot plan its labels: {e}; {REMEDY}") from e


@pytest.mark.parametrize("name", ES.RENDERS)
def test_committed_render_matches_layout(name):
    """Each committed sidecar's entries (kind, label, ``fallback``), in
    order, are ``view_dimensions``' for its route and view, and so are their
    world points; its camera is the one fitted to them now and reprojects
    them to its pixels; its resolution is the render's; the PNG is that size
    and annotated; and annotate can plan its labels on it."""
    check_render(name)


def test_a_geometry_change_fails_without_make_renders(monkeypatch):
    """N2: geometry-only changes keep every label and still fail, naming
    ``make renders``: a dimension's offset (its line moves), a camera
    bearing (every point moves) and the open-back arc's radius (its arms
    move; the label is the angle)."""
    check_render("printed-closed")
    check_render("printed-open-back")
    with monkeypatch.context() as m:
        m.setattr(ES, "DIM_OFFSET", ES.DIM_OFFSET + 1.0)
        with pytest.raises(AssertionError, match="make renders") as e:
            check_render("printed-closed")
        assert "line_a" in str(e.value)
    with monkeypatch.context() as m:
        v = ES.VIEWS["closed"]
        m.setitem(ES.VIEWS, "closed", ES.View(v.lid_deg, v.bank_out, v.azimuth_deg + 1.0,
                                              v.elevation_deg))
        with pytest.raises(AssertionError, match="make renders") as e:
            check_render("printed-closed")
        assert "azimuth_deg" in str(e.value)
    with monkeypatch.context() as m:
        m.setattr(ES, "DIM_ARC_R", ES.DIM_ARC_R + 1.0)
        with pytest.raises(AssertionError, match="make renders") as e:
            check_render("printed-open-back")
        assert " a was rendered at" in str(e.value)


def test_every_committed_render_is_known():
    """No stray render or sidecar in output/renders/ outside ``RENDERS``."""
    names = {p.name.split(".png")[0] for p in RENDERS.iterdir()}
    assert names == set(ES.RENDERS), f"output/renders/ has {sorted(names)}; {REMEDY}"


# --- the open-back arc (I1, N1) -----------------------------------------------------------

def _screen_angle(d: dict) -> float:
    c, a, b = d["centre"], d["a"], d["b"]
    va, vb = (a[0] - c[0], a[1] - c[1]), (b[0] - c[0], b[1] - c[1])
    cos = (va[0] * vb[0] + va[1] * vb[1]) / math.hypot(*va) / math.hypot(*vb)
    return math.degrees(math.acos(max(-1.0, min(1.0, cos))))


def _turn(c, a, p) -> float:
    """The signed angle (degrees) from ``c -> a`` to ``c -> p`` on screen."""
    va, vp = (a[0] - c[0], a[1] - c[1]), (p[0] - c[0], p[1] - c[1])
    return math.degrees(math.atan2(va[0] * vp[1] - va[1] * vp[0], va[0] * vp[0] + va[1] * vp[1]))


def check_arc(d: dict) -> None:
    """N1: raise AssertionError unless the arc annotate draws (``arc``)
    reads as the angle between the arms: it starts on arm ``a`` and ends on
    arm ``b``; it turns monotonically from ``a`` to ``b`` (so it stays in
    the wedge between them and goes the short way round); and every point
    is about an arm's length from the centre (ARC_RADIUS_RANGE)."""
    c, a, b, arc = d["centre"], d["a"], d["b"], d["arc"]
    assert len(arc) == DP.ARC_STEPS + 1, f"the arc has {len(arc)} points, want {DP.ARC_STEPS + 1}"
    assert _close(arc[0], a, PX_TOLERANCE) and _close(arc[-1], b, PX_TOLERANCE), \
        f"the arc runs {arc[0]} .. {arc[-1]}, not from arm a {a} to arm b {b}"
    total = _turn(c, a, b)
    assert 0 < abs(total) < 180, f"the arms are {total:.1f} deg apart on screen"
    turns = [_turn(c, a, p) * math.copysign(1.0, total) for p in arc]
    steps = [q - p for p, q in zip(turns, turns[1:])]
    assert min(steps) > 0, \
        f"the arc does not turn steadily from a to b: its points are at {turns} deg"
    assert turns[-1] == pytest.approx(abs(total))
    ra, rb = math.dist(a, c), math.dist(b, c)
    lo, hi = ARC_RADIUS_RANGE[0] * min(ra, rb), ARC_RADIUS_RANGE[1] * max(ra, rb)
    radii = [math.dist(p, c) for p in arc]
    assert lo <= min(radii) and max(radii) <= hi, \
        f"the arc's points are {min(radii):.1f} .. {max(radii):.1f} px from the centre, " \
        f"its arms {ra:.1f} and {rb:.1f} (want {lo:.1f} .. {hi:.1f})"


def _open_back_angle(route: str) -> dict:
    angles = [d for d in _sidecar(f"{route}-open-back")["dimensions"] if d["kind"] == "angle"]
    assert len(angles) == 1, f"{route}-open-back: {len(angles)} angle entries, want 1; {REMEDY}"
    return angles[0]


@pytest.mark.parametrize("route", sorted(ROUTES))
def test_open_back_arc_reads_as_its_angle(route):
    """I1: on open-back the lid-angle arc's arms, as projected, are within
    ARC_TOLERANCE_DEG of LID_OPEN_DEG, so the arc reads as that angle (on
    open-front's right face it read as about 160 degrees); N1: the arc
    annotate draws between them passes ``check_arc``."""
    d = _open_back_angle(route)
    got = _screen_angle(d)
    assert abs(got - LID_OPEN_DEG) <= ARC_TOLERANCE_DEG, \
        f"{route}-open-back: the arc's arms are {got:.1f} deg apart on screen, " \
        f"want {LID_OPEN_DEG:g} +- {ARC_TOLERANCE_DEG:g}"
    try:
        check_arc(d)
    except AssertionError as e:
        raise AssertionError(f"{route}-open-back: {e}; {REMEDY}") from e


def _reflex(d):
    """The arc the long way round: each point mirrored through the centre
    (the ends kept on the arms)."""
    c = d["centre"]
    d["arc"][1:-1] = [[2 * c[0] - p[0], 2 * c[1] - p[1]] for p in d["arc"][1:-1]]


def _reversed(d):
    d["arc"].reverse()


def _bulged(d):
    """Every interior point 40% further from the centre."""
    c = d["centre"]
    d["arc"][1:-1] = [[c[0] + 1.4 * (p[0] - c[0]), c[1] + 1.4 * (p[1] - c[1])]
                      for p in d["arc"][1:-1]]


def _scrambled(d):
    """Two of the arc's points swapped (built from the wrong points)."""
    d["arc"][5], d["arc"][20] = d["arc"][20], d["arc"][5]


def _wrong_camera(d, side):
    """The arc's world points projected by a camera turned 3 degrees about
    its view axis: the arms stay where they were."""
    cam = copy.deepcopy(side["projection"]["camera"])
    m = cam["matrix_world_m"]
    t = math.radians(3.0)
    cols = [[m[k], m[4 + k], m[8 + k]] for k in range(2)]
    r = [cols[0][k] * math.cos(t) + cols[1][k] * math.sin(t) for k in range(3)]
    u = [cols[1][k] * math.cos(t) - cols[0][k] * math.sin(t) for k in range(3)]
    for k in range(3):
        m[4 * k], m[4 * k + 1] = r[k], u[k]
    (i,) = [i for i, e in enumerate(side["dimensions"]) if e["kind"] == "angle"]
    d["arc"] = [DP.project_px(cam, tuple(v * MM for v in p))
                for p in side["projection"]["world_mm"][i]["arc"]]


@pytest.mark.parametrize("corrupt", [_reflex, _reversed, _bulged, _scrambled, _wrong_camera])
def test_check_arc_rejects_a_wrong_arc(corrupt):
    """N1: ``check_arc`` passes the committed printed open-back arc and
    fails it corrupted: drawn the reflex way, backwards, bulged, with two
    points swapped, or projected by a wrong camera (arms unchanged), so the
    arms' angle alone (I1) is no longer all that is checked."""
    side = _sidecar("printed-open-back")
    (d,) = [e for e in side["dimensions"] if e["kind"] == "angle"]
    check_arc(d)
    bad = copy.deepcopy(d)
    if corrupt is _wrong_camera:
        corrupt(bad, side)
    else:
        corrupt(bad)
    with pytest.raises(AssertionError):
        check_arc(bad)


# --- the parts the camera was fitted to (slow: every STL) ---------------------------------

SCENE = ROOT / "tmp" / "test-renders"


def _stl_bounds(path: Path) -> tuple[list[float], list[float]]:
    """A binary STL's vertex bounding box (its own units, mm)."""
    data = path.read_bytes()
    (n,) = struct.unpack_from("<I", data, 80)
    assert len(data) == 84 + 50 * n, f"{path}: not a binary STL of {n} triangles"
    lo, hi = [math.inf] * 3, [-math.inf] * 3
    for t in struct.iter_unpack("<12fH", data[84:]):
        for v in (t[3:6], t[6:9], t[9:12]):
            for k in range(3):
                lo[k], hi[k] = min(lo[k], v[k]), max(hi[k], v[k])
    return lo, hi


def _corners(m16, lo, hi) -> list[list[float]]:
    """The 8 corners of the box ``lo`` .. ``hi`` moved by ``m16`` (row
    major, mm), in metres."""
    box = [(x, y, z) for x in (lo[0], hi[0]) for y in (lo[1], hi[1]) for z in (lo[2], hi[2])]
    return [[MM * sum(m16[4 * r + c] * v for c, v in enumerate((*p, 1.0))) for r in range(3)]
            for p in box]


def scene_fit_parts(manifest: dict, base: Path) -> list[dict]:
    """What ``render_scene._camera`` records as ``fit_parts`` for
    ``manifest``: each part's and screen's world bounding-box corners."""
    out = []
    for e in manifest["parts"]:
        lo, hi = _stl_bounds(base / e["file"])
        out.append({"part": e["part"], "corners_m": _corners(e["transform"], lo, hi)})
    for s in manifest.get("screens", ()):
        q = s["quad"]
        lo = [min(p[k] for p in q) for k in range(3)]
        hi = [max(p[k] for p in q) for k in range(3)]
        out.append({"part": "screen", "corners_m": _corners(s["transform"], lo, hi)})
    return out


def check_fit_parts(name: str, got: list[dict], want: list[dict]) -> None:
    """Raise AssertionError (naming ``make renders``) unless the recorded
    ``fit_parts`` ``got`` are ``want`` (``scene_fit_parts``), corners in any
    order (Blender's ``bound_box`` order is its own)."""
    assert [e["part"] for e in got] == [e["part"] for e in want], \
        f"{name}: rendered with parts {[e['part'] for e in got]}, the scene has " \
        f"{[e['part'] for e in want]}; {REMEDY}"
    for g, w in zip(got, want):
        gs = sorted(tuple(p) for p in g["corners_m"])
        ws = sorted(tuple(p) for p in w["corners_m"])
        assert all(_close(p, q, CORNER_TOLERANCE_M) for p, q in zip(gs, ws)), \
            f"{name}: part {g['part']} was framed with corners {gs}, it is at {ws} " \
            f"now; {REMEDY}"


@pytest.fixture(scope="module")
def scene():
    return ES.export(SCENE)


@pytest.mark.slow
@pytest.mark.parametrize("name", ES.RENDERS)
def test_fit_parts_match_the_scene(name, scene):
    """N2: the parts' bounding-box corners the camera was fitted to are the
    exported scene's now (with ``check_render``'s refit, the recorded camera
    is the one ``render_scene`` would place now)."""
    manifest = json.loads(scene[name].read_text())
    check_fit_parts(name, _sidecar(name)["projection"]["fit_parts"],
                    scene_fit_parts(manifest, scene[name].parent))


def test_check_fit_parts_fails_on_a_moved_part():
    """N2: a part's bounding box moving by 0.1 mm fails ``check_fit_parts``
    naming ``make renders``."""
    parts = _sidecar("printed-closed")["projection"]["fit_parts"]
    check_fit_parts("printed-closed", parts, parts)
    moved = copy.deepcopy(parts)
    for p in moved[3]["corners_m"]:
        p[2] += 0.1 * MM
    with pytest.raises(AssertionError, match="make renders"):
        check_fit_parts("printed-closed", parts, moved)
