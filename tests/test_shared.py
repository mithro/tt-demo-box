"""Shared made parts: the screwless hinge and the loose MT1 pin.

These are printed in both routes, so every test runs against both layouts.
"""

import importlib.util
import math

import cadquery as cq
import pytest
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

from demobox import checks as C
from demobox import layout as L
from demobox.parts.batteries import BATTERIES
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


def _inside(shape: cq.Shape, x, y, z) -> bool:
    return shape.isInside(cq.Vector(x, y, z))


def _axis(lay, part):
    return lay.hinge_axis if part == "base" else (0.0, 0.0)


def _rod(lay) -> cq.Solid:
    """The rod, PIN_ROD_D, from the +X side face back ``pin_length`` (base frame)."""
    n = H.pin_length(lay)
    return cq.Solid.makeCylinder(L.PIN_ROD_D / 2, n, cq.Vector(lay.outer.x1 - n, *lay.hinge_axis),
                                 cq.Vector(1, 0, 0))


def _lid_at(lay, angle) -> cq.Shape:
    return _compound(H.knuckles(lay, "lid")).moved(lay.lid_location(angle))


def _parts(lay, part):
    return [k for k in H.knuckle_plan(lay) if k.part == part]


def _bead(lay) -> cq.Shape:
    return _compound(H.seal_bead(lay))


# --- removed parts -----------------------------------------------------------------

@pytest.mark.parametrize("name", ["m3", "inserts", "packing"])
def test_no_screw_or_packing_modules(name):
    """Goal 3: no screws, nuts or inserts; the bank packing is gone too."""
    assert importlib.util.find_spec(f"demobox.shared.{name}") is None


# --- the knuckle plan ---------------------------------------------------------------

def test_knuckles_alternate_and_skip_notch(lay):
    """R15, R19: knuckles only in ``knuckle_x``, alternating base/lid along X,
    FIT apart, none across the pigtail's notch.  Each range long enough for
    one is filled by as many knuckles of at least KNUCKLE_LEN as fit, sharing
    it equally with FIT gaps, so the end knuckles are flush with the range's
    ends (a side face included).  (Not "the whole axis": everywhere off
    ``knuckle_x`` is open.)"""
    plan = H.knuckle_plan(lay)
    assert [k.x0 for k in plan] == sorted(k.x0 for k in plan)
    assert {k.part for k in plan} == {"base", "lid"}
    for a, b in zip(plan, plan[1:]):
        assert a.part != b.part
        assert b.x0 - a.x1 >= L.FIT - EPS              # never overlap; FIT between
    n = lay.hinge_notch
    for k in plan:
        assert k.x1 - k.x0 >= L.KNUCKLE_LEN - EPS
        assert k.x1 - k.x0 < 2 * L.KNUCKLE_LEN + L.FIT   # else it would be two
        assert k.x1 <= n.x0 + EPS or k.x0 >= n.x1 - EPS
        assert any(x0 - EPS <= k.x0 and k.x1 <= x1 + EPS for x0, x1 in lay.knuckle_x)
    for x0, x1 in lay.knuckle_x:
        inside = [k for k in plan if x0 - EPS <= k.x0 and k.x1 <= x1 + EPS]
        if x1 - x0 < L.KNUCKLE_LEN:
            assert not inside
            continue
        assert inside[0].x0 == pytest.approx(x0) and inside[-1].x1 == pytest.approx(x1)
        for a, b in zip(inside, inside[1:]):
            assert b.x0 - a.x1 == pytest.approx(L.FIT)
        assert len({round(k.x1 - k.x0, 9) for k in inside}) == 1


def test_knuckle_plan_printed():
    """The printed route's plan, by hand from ``knuckle_x`` (R19, R23:
    155.9..175.35, 181.35..197.7): range 1 (19.45) holds two, (19.45 - FIT)
    / 2 = 9.475 each; range 2 (16.35) one, flush with the right side face.
    Lid, base, lid: two stops, the base knuckle caught between them."""
    plan = H.knuckle_plan(L.layout(L.ROUTES["printed"]))
    got = [(round(k.x0, 3), round(k.x1, 3), k.part) for k in plan]
    assert got == [(155.9, 165.375, "lid"), (165.875, 175.35, "base"), (181.35, 197.7, "lid")]


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
    plan = H.knuckle_plan(lay)
    base = _solids(H.knuckles(lay, "base"))
    lid = _solids(H.knuckles(lay, "lid"))
    assert len(base) == len(plan)                # base knuckles + one stop per lid knuckle
    assert len(lid) == len(_parts(lay, "lid"))
    for part, solids in (("base", base), ("lid", lid)):
        comp = cq.Compound.makeCompound(solids)
        origin = _axis(lay, part)
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


# --- the rod ----------------------------------------------------------------------

def test_pin_flush(lay):
    """R22, R24: one rod from the blind end of the first knuckle's bore
    (ROD_BLIND in from its -X face) to the +X side face, flush there (it
    goes in from there)."""
    first = H.knuckle_plan(lay)[0]
    assert H.ROD_BLIND == 1.0
    x0 = lay.outer.x1 - H.pin_length(lay)
    assert x0 == pytest.approx(first.x0 + H.ROD_BLIND)
    assert first.x0 < x0 < first.x1


def _cyl(lay, part, d, x0, x1) -> cq.Solid:
    """A cylinder of diameter d on the axis, x0..x1, in ``part``'s frame."""
    return cq.Solid.makeCylinder(d / 2, x1 - x0, cq.Vector(x0, *_axis(lay, part)),
                                 cq.Vector(1, 0, 0))


def test_rod_bore_slip_fit(lay):
    """PIN_HOLE_D = PIN_ROD_D + 0.2 through every knuckle but the press zone:
    the rod is clear there, a ring just outside the bore is not."""
    assert H.PIN_HOLE_D == pytest.approx(L.PIN_ROD_D + 0.2)
    x0 = lay.outer.x1 - H.pin_length(lay)
    slip_x1 = lay.outer.x1 - H.PRESS_LEN
    for part in ("base", "lid"):
        comp = _compound(H.knuckles(lay, part))
        assert _common(_cyl(lay, part, L.PIN_ROD_D, x0, slip_x1), comp) <= 1e-6, part
        for k in _parts(lay, part):
            ring = _cyl(lay, part, H.PIN_HOLE_D + 0.1, k.x0 + 0.1, k.x1 - 0.1).cut(
                _cyl(lay, part, H.PIN_HOLE_D + 0.02, k.x0, k.x1))
            assert _common(ring, comp) > 0, (part, k)


def test_rod_blind_end(lay):
    """R24: the first knuckle's bore stops ROD_BLIND short of its -X face: a
    rod a little longer than ``pin_length`` meets solid there."""
    first = H.knuckle_plan(lay)[0]
    comp = _compound(H.knuckles(lay, first.part))
    blind = _cyl(lay, first.part, L.PIN_ROD_D, first.x0 + 0.01, first.x0 + H.ROD_BLIND - 0.01)
    assert _common(blind, comp) == pytest.approx(blind.Volume(), rel=1e-3)
    longer = _cyl(lay, first.part, L.PIN_ROD_D, lay.outer.x1 - H.pin_length(lay) - 0.2,
                  lay.outer.x1 - H.PRESS_LEN)
    assert _common(longer, comp) > 0.1


def test_rod_press_fit(lay):
    """R24: the last PRESS_LEN of the +X knuckle's bore, at the side face, is
    PIN_ROD_D - 0.1: narrower than the rod all the way, and the slip bore
    starts right after it."""
    last = H.knuckle_plan(lay)[-1]
    assert last.x1 == pytest.approx(lay.outer.x1)
    assert H.PRESS_D == pytest.approx(L.PIN_ROD_D - 0.1) and H.PRESS_LEN == 5.0
    comp = _compound(H.knuckles(lay, last.part))
    x1 = lay.outer.x1
    ring = _cyl(lay, last.part, L.PIN_ROD_D, x1 - H.PRESS_LEN + 0.01, x1 - 0.01).cut(
        _cyl(lay, last.part, H.PRESS_D + 0.02, x1 - H.PRESS_LEN, x1))
    assert _common(ring, comp) == pytest.approx(ring.Volume(), rel=1e-3)
    inside = _cyl(lay, last.part, H.PRESS_D - 0.02, x1 - H.PRESS_LEN, x1)
    assert _common(inside, comp) <= 1e-6
    slip = _cyl(lay, last.part, H.PIN_HOLE_D - 0.02, last.x0, x1 - H.PRESS_LEN - 0.01)
    assert _common(slip, comp) <= 1e-6


def test_rod_enclosed_by_knuckles(lay):
    """R22: along its length the rod is in a knuckle everywhere but the
    pigtail's notch and the FIT gaps between knuckles."""
    plan = H.knuckle_plan(lay)
    n = lay.hinge_notch
    x0 = lay.outer.x1 - H.pin_length(lay)
    x = x0
    for a, b in sorted([(k.x0, k.x1) for k in plan] + [(n.x0, n.x1)]):
        assert a - x <= L.FIT + EPS, (x, a)                 # at most a FIT gap
        x = max(x, b)
    assert x == pytest.approx(lay.outer.x1)
    exposed = (lay.outer.x1 - x0) - sum(k.x1 - k.x0 for k in plan) - (n.x1 - n.x0)
    assert exposed <= (len(plan) - 1) * L.FIT + EPS


@pytest.mark.parametrize("corner", [(0, 0), (0, 1), (1, 0), (1, 1)],
                         ids=["-x-y", "-x+y", "+x-y", "+x+y"])
def test_bank_anywhere_in_its_bay_misses_the_hinge(lay, corner):
    """R19, R22, R23: the bank pushed into any corner of its bay (along X
    and Y) stays at least FIT off every knuckle, closed and at the stop, and
    off the rod."""
    l_, w_, h_ = BATTERIES[L.DESIGN_BANK].size
    bay = lay.bank_bay
    x0 = bay.x1 - l_ if corner[0] else bay.x0
    y0 = bay.y1 - w_ if corner[1] else bay.y0
    bank = _box(x0, y0, bay.z0, x0 + l_, y0 + w_, bay.z0 + h_)
    assert _dist(bank, _compound(H.knuckles(lay, "base"))) >= L.FIT - EPS
    assert _dist(bank, _rod(lay)) >= L.FIT - EPS
    for a in (0.0, L.LID_OPEN_DEG):
        assert _dist(bank, _lid_at(lay, a)) >= L.FIT - EPS, a


# --- the cuts -----------------------------------------------------------------------

def test_knuckle_cut_is_the_r21_relief(lay):
    """R21: the base is cut back to ``hinge_relief_r`` only at the lid
    knuckles (FIT past each end); the lid everywhere but its own knuckles
    (the base knuckles, the FIT gaps, the open segments).  Each cut also
    bores the rod's hole through every knuckle."""
    rr = lay.hinge_relief_r
    plan = H.knuckle_plan(lay)
    # the FIT gaps between interleaved knuckles (not the notch: that is open)
    gaps = [(a.x1, b.x0) for a, b in zip(plan, plan[1:]) if b.x0 - a.x1 <= L.FIT + EPS]
    assert gaps
    w = lay.outer.size[0]
    s, c = math.sin(math.radians(30)), math.cos(math.radians(30))
    opens = [x for x in (0.5, w / 2) if not any(k.x0 - L.FIT <= x <= k.x1 + L.FIT for k in plan)]
    assert opens
    for part, v in (("base", -1.0), ("lid", 1.0)):
        y0, z0 = _axis(lay, part)
        cut = _compound(H.knuckle_cut(lay, part))
        # just inside the relief radius, on this part's side of the seam
        probe = (y0 - (rr - 0.1) * s, z0 + v * (rr - 0.1) * c)
        for k in plan:
            xm = (k.x0 + k.x1) / 2
            assert _inside(cut, xm, *probe) == (k.part != part), (part, k)
            assert _inside(cut, xm, y0, z0), (part, k, "bore")
        for a, b in gaps:
            assert _inside(cut, (a + b) / 2, *probe), (part, a, b)
        for x in opens:
            assert _inside(cut, x, *probe) == (part == "lid"), (part, x)
        far = (y0 - (rr + 0.1) * s, z0 + v * (rr + 0.1) * c)
        for k in plan:
            assert not _inside(cut, (k.x0 + k.x1) / 2, *far), part


# --- the seal bead (R21) --------------------------------------------------------------

def test_seal_bead_inside_the_closed_box(lay):
    """Above the seam, inside the outline and the closed lid, and not over the
    bank row, so the bank still lifts straight out (R12)."""
    hz = lay.hinge_axis[1]
    o, lo = lay.outer, lay.lid_outer
    bb = _bead(lay).BoundingBox()
    assert bb.xmin >= o.x0 - EPS and bb.xmax <= o.x1 + EPS
    assert bb.ymin >= max(lay.bank_bay.y1, lay.port_room.y1) - EPS and bb.ymax <= o.y1 + EPS
    assert bb.zmin >= hz - EPS and bb.zmax <= hz + lo.z1 + EPS
    assert bb.zmax - hz <= lay.hinge_relief_r - L.FIT + EPS


def test_seal_bead_runs_the_open_segments(lay):
    """Along every open segment; not at a knuckle (nor FIT either side of
    one) and not across the pigtail's notch."""
    hy, hz = lay.hinge_axis
    bead = _bead(lay)
    plan = H.knuckle_plan(lay)
    n = lay.hinge_notch
    w = lay.outer.size[0]
    edges = [e for k in plan for e in (k.x0 - L.FIT, k.x1 + L.FIT)] + [n.x0, n.x1]
    xs = [(i + 0.5) / 4 for i in range(int(w * 4))]
    for x in xs:
        if any(abs(x - e) < 0.01 for e in edges):
            continue
        near = any(k.x0 - L.FIT <= x <= k.x1 + L.FIT for k in plan)
        notch = n.x0 <= x <= n.x1
        if not near and not notch:
            assert _inside(bead, x, hy + 1.0, hz + 1.0), x
        if near or notch:
            assert not _inside(bead, x, hy + 1.0, hz + 1.0), x


def test_seal_bead_clears_the_pigtail(lay):
    """The pigtail's centreline stays a cable radius off the bead at every
    sweep angle."""
    bead = _bead(lay)
    for a in L.sweep_angles():
        pts = C.pigtail_path(lay, a)
        for p, q in zip(pts, pts[1:]):
            leg = cq.Edge.makeLine(cq.Vector(*p), cq.Vector(*q))
            assert _dist(leg, bead) > C.PIGTAIL.dia / 2, (a, p, q)


def test_back_closed_in_open_segments(lay):
    """A YZ section through an open segment, the box closed: across the
    back wall (the outer ``wall`` of the back face) everything is base, bead
    or lid but the FIT running clearance between the bead and the lid's
    relief."""
    hy, hz = lay.hinge_axis
    rr, rb = lay.hinge_relief_r, lay.hinge_relief_r - L.FIT
    x = lay.outer.size[0] / 2
    assert not any(k.x0 - L.FIT <= x <= k.x1 + L.FIT for k in H.knuckle_plan(lay))
    base, lid = _base_worst(lay), _lid_worst(lay).moved(lay.lid_location(0))
    top = hz + lay.lid_outer.z1
    for u in (L.KNUCKLE_R - lay.wall + 0.05, L.KNUCKLE_R - lay.wall / 2, L.KNUCKLE_R - 0.05):
        for i in range(int((top - (hz - rr - 2.0)) / 0.1)):
            v = -rr - 2.0 + 0.05 + i * 0.1
            if hz + v >= top:
                break
            r = math.hypot(u, v)
            if rb - 0.01 < r < rr + 0.01:
                continue                                    # the running clearance
            assert _inside(base, x, hy + u, hz + v) or _inside(lid, x, hy + u, hz + v), (u, v)


# --- the swing and the stop ---------------------------------------------------------

def _base_worst(lay) -> cq.Shape:
    """The base as if solid everywhere: its outer box less its cut, with its
    knuckles (and stop blocks) and its seal bead added."""
    o = lay.outer
    solid = _box(o.x0, o.y0, o.z0, o.x1, o.y1, o.z1).cut(_compound(H.knuckle_cut(lay, "base")))
    return solid.fuse(_compound(H.knuckles(lay, "base"))).fuse(_bead(lay))


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


@pytest.mark.parametrize("angle", [0, 20, 40, 60, 80, 100])
def test_lid_never_meets_the_bead(lay, angle):
    """The lid, as if solid everywhere less its cut, misses the bead to the
    stop (every degree is ``checks.hinge_sweep``'s, in YZ)."""
    lid = _lid_worst(lay).moved(lay.lid_location(angle))
    assert _common(lid, _bead(lay)) <= 1e-6
    assert _dist(lid, _bead(lay)) >= L.FIT - 0.01


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
    """The base knuckles, stop blocks and bead miss every base content; the
    lid knuckles miss the monitor and, when it is in the lid, the boost
    pocket."""
    base = _compound(H.knuckles(lay, "base"))
    bead = _bead(lay)
    for name, b in L.base_contents(lay).items():
        box = _box(b.x0, b.y0, b.z0, b.x1, b.y1, b.z1)
        assert _common(base, box) <= 1e-6, name
        assert _common(bead, box) <= 1e-6, name
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
