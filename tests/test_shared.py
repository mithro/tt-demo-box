"""Shared made parts: the screwless hinge and the loose MT1 pin.

These are printed in both routes, so every test runs against both layouts.
"""

import importlib.util
import math

import cadquery as cq
import pytest
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

from demobox import layout as L
from demobox.parts.board import BOARD_KEYS, board_spec
from demobox.shared import hinge as H
from demobox.shared import pin

#: "touch": closer than this ...
TOUCH = 0.05
#: ... with no more interpenetration than this (mm^3).
VOL_TOL = 0.01
EPS = 1e-6


@pytest.fixture(params=sorted(L.ROUTES.items()), ids=lambda r: r[0])
def lay(request):
    return L.layout(request.param[1])


def _solids(wp: cq.Workplane) -> list[cq.Solid]:
    solids = wp.solids().vals()
    assert solids
    for s in solids:
        assert s.isValid()
        assert s.Volume() > 0
    return solids


def _compound(wp: cq.Workplane) -> cq.Compound:
    return cq.Compound.makeCompound(_solids(wp))


def _dist(a: cq.Shape, b: cq.Shape) -> float:
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    assert d.IsDone()
    return d.Value()


def _common(a: cq.Shape, b: cq.Shape) -> float:
    return a.intersect(b).Volume()


def _box(x0, y0, z0, x1, y1, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _lid_at(lay, angle) -> cq.Shape:
    return _compound(H.knuckles(lay, "lid")).moved(lay.lid_location(angle))


def _parts(lay, part):
    return [k for k in H.knuckle_plan(lay) if k.part == part]


# --- removed parts -----------------------------------------------------------------

@pytest.mark.parametrize("name", ["m3", "inserts", "packing"])
def test_no_screw_or_packing_modules(name):
    """Goal 3: no screws, nuts or inserts; the bank packing is gone too."""
    assert importlib.util.find_spec(f"demobox.shared.{name}") is None


# --- the knuckle plan ---------------------------------------------------------------

def test_knuckles_alternate_and_skip_notch(lay):
    """R15: knuckles only in ``knuckle_x``, alternating base/lid along X, FIT
    apart, none across the pigtail's notch; each range holds as many
    KNUCKLE_LEN knuckles as fit, and one touching a side face is flush with
    it.  (Not "the whole axis": everywhere off ``knuckle_x`` is open.)"""
    plan = H.knuckle_plan(lay)
    assert [k.x0 for k in plan] == sorted(k.x0 for k in plan)
    assert {k.part for k in plan} == {"base", "lid"}
    for a, b in zip(plan, plan[1:]):
        assert a.part != b.part
        assert b.x0 - a.x1 >= L.FIT - EPS              # never overlap; FIT between
    n = lay.hinge_notch
    for k in plan:
        assert k.x1 - k.x0 == pytest.approx(L.KNUCKLE_LEN)
        assert k.x1 <= n.x0 + EPS or k.x0 >= n.x1 - EPS
        assert any(x0 - EPS <= k.x0 and k.x1 <= x1 + EPS for x0, x1 in lay.knuckle_x)
    for x0, x1 in lay.knuckle_x:
        inside = [k for k in plan if x0 - EPS <= k.x0 and k.x1 <= x1 + EPS]
        free = (x1 - x0) - sum(k.x1 - k.x0 + L.FIT for k in inside) + L.FIT
        assert free < L.KNUCKLE_LEN + L.FIT, (x0, x1, "room for another knuckle")
        if inside and x1 == lay.outer.x1:
            assert inside[-1].x1 == pytest.approx(lay.outer.x1)
        if inside and x0 == lay.outer.x0:
            assert inside[0].x0 == pytest.approx(lay.outer.x0)


def test_knuckle_plan_printed():
    """The printed route's plan, by hand from ``knuckle_x`` (154.4..175.35,
    181.35..197.7): range 1 holds 10 + FIT + 10 = 20.5 of its 20.95, pushed
    against the notch; range 2 one knuckle, flush with the right side face.
    Lid, base, lid: two stops, the base knuckle caught between them."""
    plan = H.knuckle_plan(L.layout(L.ROUTES["printed"]))
    got = [(round(k.x0, 3), round(k.x1, 3), k.part) for k in plan]
    assert got == [(154.85, 164.85, "lid"), (165.35, 175.35, "base"), (187.7, 197.7, "lid")]


def test_knuckles_inside_outer(lay):
    """Nothing proud of the closed box.  The axis is on the seam, so a
    knuckle round it is half in the base and half in the lid: each part's
    knuckles lie within ``outer`` in X and Y and within the closed box
    (base + lid) in Z."""
    hz = lay.hinge_axis[1]
    o, lo = lay.outer, lay.lid_outer
    bb = _compound(H.knuckles(lay, "base")).BoundingBox()
    assert (bb.xmin, bb.ymin, bb.zmin) >= (o.x0 - EPS, o.y0 - EPS, o.z0 - EPS)
    assert bb.xmax <= o.x1 + EPS and bb.ymax <= o.y1 + EPS and bb.zmax <= hz + lo.z1 + EPS
    bb = _compound(H.knuckles(lay, "lid")).BoundingBox()          # lid frame, closed
    assert bb.xmin >= lo.x0 - EPS and bb.ymin >= lo.y0 - EPS and bb.zmin >= -hz - EPS
    assert bb.xmax <= lo.x1 + EPS and bb.ymax <= lo.y1 + EPS and bb.zmax <= lo.z1 + EPS


def test_knuckles_where_the_plan_says(lay):
    """One solid per knuckle round the axis over its X range; the base also
    carries a stop block under each lid knuckle."""
    hy, hz = lay.hinge_axis
    plan = H.knuckle_plan(lay)
    base = _solids(H.knuckles(lay, "base"))
    lid = _solids(H.knuckles(lay, "lid"))
    assert len(base) == len(plan)                # base knuckles + one stop per lid knuckle
    assert len(lid) == len(_parts(lay, "lid"))
    for part, solids, origin in (("base", base, (hy, hz)), ("lid", lid, (0.0, 0.0))):
        comp = cq.Compound.makeCompound(solids)
        for k in plan:
            # a ring between the bore and KNUCKLE_R, on the axis, in this knuckle
            ring = cq.Solid.makeCylinder(L.KNUCKLE_R - 0.2, k.x1 - k.x0 - 0.2,
                                         cq.Vector(k.x0 + 0.1, *origin), cq.Vector(1, 0, 0)).cut(
                cq.Solid.makeCylinder(H.PIN_HOLE_D / 2 + 0.2, k.x1 - k.x0,
                                      cq.Vector(k.x0, *origin), cq.Vector(1, 0, 0)))
            vol = _common(ring, comp)
            if k.part == part:
                assert vol == pytest.approx(ring.Volume(), rel=1e-3), (part, k)
            else:
                assert vol <= VOL_TOL, (part, k)


def test_rod_bore(lay):
    """PIN_HOLE_D = PIN_ROD_D + 0.2 along the axis through every knuckle: the
    rod is clear, a ring just outside the bore is not."""
    assert H.PIN_HOLE_D == pytest.approx(L.PIN_ROD_D + 0.2)
    hy, hz = lay.hinge_axis
    w = lay.outer.size[0]
    for part, origin in (("base", (hy, hz)), ("lid", (0.0, 0.0))):
        comp = _compound(H.knuckles(lay, part))
        rod = cq.Solid.makeCylinder(L.PIN_ROD_D / 2, w, cq.Vector(0.0, *origin),
                                    cq.Vector(1, 0, 0))
        assert _common(rod, comp) <= 1e-6, part
        for k in _parts(lay, part):
            ring = cq.Solid.makeCylinder(H.PIN_HOLE_D / 2 + 0.05, k.x1 - k.x0 - 0.2,
                                         cq.Vector(k.x0 + 0.1, *origin),
                                         cq.Vector(1, 0, 0)).cut(
                cq.Solid.makeCylinder(H.PIN_HOLE_D / 2 + 0.01, k.x1 - k.x0,
                                      cq.Vector(k.x0, *origin), cq.Vector(1, 0, 0)))
            assert _common(ring, comp) > 0, (part, k)


def test_pin_flush(lay):
    """One full-width rod (R18), flush with both side faces."""
    assert H.pin_length(lay) == lay.outer.size[0]


# --- the cuts -----------------------------------------------------------------------

def _inside(shape: cq.Shape, x, y, z) -> bool:
    return shape.isInside(cq.Vector(x, y, z))


def test_knuckle_cut_is_the_r15_relief(lay):
    """Each part is cut back to ``hinge_relief_r`` round the axis wherever it
    has no knuckle: at the other part's knuckles, in the FIT gaps between
    knuckles and in the open segments; never at its own knuckles.  The cut
    also bores the rod's hole the full width."""
    hy, hz = lay.hinge_axis
    rr = lay.hinge_relief_r
    plan = H.knuckle_plan(lay)
    gaps = [(a.x1, b.x0) for a, b in zip(plan, plan[1:])]
    w = lay.outer.size[0]
    s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
    for part, (y0, z0), v in (("base", (hy, hz), -1.0), ("lid", (0.0, 0.0), 1.0)):
        cut = _compound(H.knuckle_cut(lay, part))
        # just inside the relief radius, on this part's side of the seam
        probe = (y0 - (rr - 0.1) * s, z0 + v * (rr - 0.1) * c)
        for k in plan:
            xm = (k.x0 + k.x1) / 2
            assert _inside(cut, xm, *probe) == (k.part != part), (part, k)
            assert _inside(cut, xm, y0, z0), (part, k, "bore")
        for a, b in gaps:
            assert _inside(cut, (a + b) / 2, *probe), (part, a, b)
        for x in (0.5, w / 2, w - 0.5):
            if not any(k.x0 <= x <= k.x1 for k in plan):
                assert _inside(cut, x, *probe), (part, x)
        # not beyond the relief radius
        far = (y0 - (rr + 0.1) * s, z0 + v * (rr + 0.1) * c)
        assert not _inside(cut, w / 2, *far), part


# --- the swing and the stop ---------------------------------------------------------

def _base_worst(lay) -> cq.Shape:
    """The base as if solid everywhere: its outer box less its cut, with its
    knuckles (and stop blocks) added."""
    o = lay.outer
    solid = _box(o.x0, o.y0, o.z0, o.x1, o.y1, o.z1).cut(_compound(H.knuckle_cut(lay, "base")))
    return solid.fuse(_compound(H.knuckles(lay, "base")))


def _lid_worst(lay) -> cq.Shape:
    lo = lay.lid_outer
    solid = _box(lo.x0, lo.y0, lo.z0, lo.x1, lo.y1, lo.z1).cut(
        _compound(H.knuckle_cut(lay, "lid")))
    return solid.fuse(_compound(H.knuckles(lay, "lid")))


@pytest.mark.parametrize("angle", [0, 15, 30, 45, 60, 75, 90, 99])
def test_knuckles_swing_clear_of_the_other_part(lay, angle):
    """Short of the stop, each part's knuckles miss the other part taken as
    solid everywhere (its box less its knuckle cut, plus its knuckles)."""
    assert _common(_lid_at(lay, angle), _base_worst(lay)) <= VOL_TOL
    lid = _lid_worst(lay).moved(lay.lid_location(angle))
    assert _common(lid, _compound(H.knuckles(lay, "base"))) <= VOL_TOL


def test_stop_at_100(lay):
    """The integral stop: each lid knuckle's tab lands on the base's stop
    block at LID_OPEN_DEG.  A degree short they don't touch; at it they
    touch; a degree past they interfere."""
    base = _compound(H.knuckles(lay, "base"))
    a = L.LID_OPEN_DEG
    assert _dist(_lid_at(lay, a - 1), base) > TOUCH
    at = _lid_at(lay, a)
    assert _dist(at, base) <= TOUCH
    assert _common(at, base) <= VOL_TOL
    assert _common(_lid_at(lay, a + 1), base) > VOL_TOL


def test_stop_faces_are_the_knuckles(lay):
    """``stop_faces``: one per lid knuckle, over its X range; its block is in
    the base knuckles and its tab in the lid knuckles."""
    lids = _parts(lay, "lid")
    stops = H.stop_faces(lay)
    assert [(s.x0, s.x1) for s in stops] == [(k.x0, k.x1) for k in lids]
    base = _compound(H.knuckles(lay, "base"))
    lid = _compound(H.knuckles(lay, "lid"))
    for s in stops:
        xm = (s.x0 + s.x1) / 2
        for poly, comp in ((s.block, base), (s.tab, lid)):
            cy = sum(p[0] for p in poly) / len(poly)
            cz = sum(p[1] for p in poly) / len(poly)
            assert _inside(comp, xm, cy, cz), (s, poly)


# --- clear of everything else ------------------------------------------------------

def test_knuckles_clear_the_contents(lay):
    """The base knuckles and stop blocks miss every base content; the lid
    knuckles miss the monitor and, when it is in the lid, the boost pocket."""
    base = _compound(H.knuckles(lay, "base"))
    for name, b in L.base_contents(lay).items():
        assert _common(base, _box(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1)) <= 1e-6, name
    lid = _compound(H.knuckles(lay, "lid"))
    boxes = {"monitor": lay.monitor_space}
    if lay.boost_in_lid:
        boxes["boost pocket"] = lay.boost_pocket
    for name, b in boxes.items():
        assert _common(lid, _box(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1)) <= 1e-6, name


@pytest.mark.parametrize("angle", [0.0, 50.0, L.LID_OPEN_DEG])
def test_pigtail_clears_the_knuckles(lay, angle):
    """The monitor's pigtail (``checks.pigtail_path``, its centreline) stays
    a cable radius off every knuckle, closed, half open and at the stop."""
    from demobox import checks as C
    pts = C.pigtail_path(lay, angle)
    shapes = (_lid_at(lay, angle), _compound(H.knuckles(lay, "base")))
    for p, q in zip(pts, pts[1:]):
        leg = cq.Edge.makeLine(cq.Vector(*p), cq.Vector(*q))
        for s in shapes:
            assert _dist(leg, s) > C.PIGTAIL.dia / 2, (p, q)


# --- MT1 locating pin ----------------------------------------------------------------

def test_locating_pin_height(lay):
    """Seated at the bottom of its plinth hole, the loose pin stands PIN_PROUD
    above the PCB top (each revision's), PEG_DIA across."""
    s = _solids(pin.locating_pin(lay))[0]
    bb = s.BoundingBox()
    assert bb.xmax - bb.xmin == pytest.approx(L.PEG_DIA)
    assert bb.ymax - bb.ymin == pytest.approx(L.PEG_DIA)
    assert bb.zmin == pytest.approx(0.0)
    seat = lay.plinth.z1 - pin.socket_depth(lay)
    assert lay.plinth.z0 - EPS <= seat < lay.plinth.z1
    for k in BOARD_KEYS:
        pcb_top = lay.board_origin[2] + board_spec(k).outline.thickness
        assert seat + bb.zmax == pytest.approx(pcb_top + L.PIN_PROUD), k
        assert lay.pins[f"{k}/MT1"].z1 == pytest.approx(seat + bb.zmax), k
    assert math.isclose(s.Volume(), math.pi * (L.PEG_DIA / 2) ** 2 * bb.zmax, rel_tol=0.05)
