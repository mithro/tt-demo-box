"""Shared made parts: hinge, monitor inserts, battery packing, MT1 pin.

These are printed in both routes, so every test runs against both layouts.
"""

import math

import cadquery as cq
import pytest
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepExtrema import BRepExtrema_DistShapeShape

from demobox import checks as C
from demobox import layout as L
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS
from demobox.shared import hinge as H
from demobox.shared import m3
from demobox.shared import inserts as I
from demobox.shared import packing as P
from demobox.shared import pin

#: "touch": closer than this ...
TOUCH = 0.05
#: ... with no more interpenetration than this (mm^3).
VOL_TOL = 0.01
EPS = 1e-6


@pytest.fixture(params=sorted(L.ROUTES.items()), ids=lambda r: r[0])
def lay(request):
    return L.layout(request.param[1])


def _one_valid_solid(wp: cq.Workplane) -> cq.Solid:
    solids = wp.solids().vals()
    assert len(solids) == 1, f"{len(solids)} solids"
    s = solids[0]
    assert s.isValid()
    assert s.Volume() > 0
    return s


def _dist(a: cq.Shape, b: cq.Shape) -> float:
    d = BRepExtrema_DistShapeShape(a.wrapped, b.wrapped)
    d.Perform()
    assert d.IsDone()
    return d.Value()


def _common(a: cq.Shape, b: cq.Shape) -> float:
    return a.intersect(b).Volume()


def _box(x0, y0, z0, x1, y1, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


# --- hinge -----------------------------------------------------------------------

def _lid_at(lay, angle):
    return H.hinge_lid_knuckles(lay).val().moved(lay.lid_location(angle))


def test_hinge_parts_are_one_valid_solid_each(lay):
    _one_valid_solid(H.hinge_base_knuckles(lay))
    _one_valid_solid(H.hinge_lid_knuckles(lay))


def test_hinge_stop_touches_at_lid_open_deg(lay):
    base = H.hinge_base_knuckles(lay).val()
    lid = _lid_at(lay, L.LID_OPEN_DEG)
    assert _dist(lid, base) < TOUCH
    assert _common(lid, base) <= VOL_TOL


def test_hinge_stop_clear_one_degree_short(lay):
    base = H.hinge_base_knuckles(lay).val()
    assert _dist(_lid_at(lay, L.LID_OPEN_DEG - 1), base) > TOUCH


@pytest.mark.parametrize("angle", [0, 10, 20, 30, 40, 45, 50, 56, 60, 70, 80, 90, 95, 99])
def test_hinge_swings_without_interference(lay, angle):
    base = H.hinge_base_knuckles(lay).val()
    assert _common(_lid_at(lay, angle), base) <= VOL_TOL


def test_hinge_stop_blocks_past_lid_open_deg(lay):
    base = H.hinge_base_knuckles(lay).val()
    assert _common(_lid_at(lay, L.LID_OPEN_DEG + 2), base) > VOL_TOL


def test_hinge_knuckles_on_the_axis_clear_of_the_cable_channel(lay):
    hy, hz = lay.hinge_axis
    ch = lay.hinge_cable_channel
    groups = H.hinge_groups(lay)
    assert len(groups) >= 2
    for x0, x1 in groups:
        assert x1 <= ch.x0 - L.FIT + EPS or x0 >= ch.x1 + L.FIT - EPS
    # the knuckles are round the hinge axis: a knuckle-sized rod on the axis
    # across each group meets both parts
    base = H.hinge_base_knuckles(lay).val()
    lid = H.hinge_lid_knuckles(lay).val()
    for x0, x1 in groups:
        rod = cq.Solid.makeCylinder(H.KNUCKLE_R, x1 - x0, cq.Vector(x0, hy, hz),
                                    cq.Vector(1, 0, 0))
        assert _common(rod, base) > 0
        assert _common(rod.moved(lay.lid_location(0).inverse), lid) > 0


def test_hinge_pin_m3_bolt_passes_every_knuckle(lay):
    hy, hz = lay.hinge_axis
    base = H.hinge_base_knuckles(lay).val()
    lid = H.hinge_lid_knuckles(lay).val()
    for x0, x1 in H.hinge_groups(lay):
        # M3 shank (3.0 mm) along the axis, past both ends of the group
        shank = cq.Solid.makeCylinder(1.5, x1 - x0 + 10, cq.Vector(x0 - 5, hy, hz),
                                      cq.Vector(1, 0, 0))
        assert _common(shank, base) <= VOL_TOL
        assert _common(shank.moved(lay.lid_location(0).inverse), lid) <= VOL_TOL
    length = H.hinge_bolt_length(lay)
    assert length in m3.LENGTHS
    g = max(x1 - x0 for x0, x1 in H.hinge_groups(lay))
    assert length >= g + H.NYLOC_H + H.THREAD_PAST - EPS


def test_hinge_leaves_have_screw_holes(lay):
    # each leaf is pierced (along Y, through the leaf) by M3 clearance holes
    for wp in (H.hinge_base_knuckles(lay), H.hinge_lid_knuckles(lay)):
        holes = []
        for f in wp.faces("%CYLINDER").vals():
            c = BRepAdaptor_Surface(f.wrapped).Cylinder()
            d = c.Axis().Direction()
            if abs(c.Radius() - H.SCREW_HOLE_D / 2) < 1e-6 and abs(abs(d.Y()) - 1) < 1e-9:
                holes.append(f)
        assert len(holes) >= 2


# --- monitor bezel ------------------------------------------------------------------

def _opening(lay):
    boxes = [lay.lid_pocket, *lay.lid_cable_gutters.values()]
    return (min(b.x0 for b in boxes), min(b.y0 for b in boxes),
            max(b.x1 for b in boxes), max(b.y1 for b in boxes))


def _panel_rect_in_lid(m, lay, rect):
    """A (w, h, x, y) rect in the panel's front frame -> lid (x0, y0, x1, y1)."""
    w, h, x, y = rect
    pb = C.panel_in_lid(m, lay)
    return (pb.x0 + x, pb.y1 - y - h, pb.x0 + x + w, pb.y1 - y)


def _inner_wires(wp):
    face = wp.faces("<Z").val()
    out = []
    for wire in face.innerWires():
        bb = wire.BoundingBox()
        out.append((bb.xmin, bb.ymin, bb.xmax, bb.ymax))
    return out


def _is_screw_hole(r, lay):
    d = I.BEZEL_SCREW_D
    return any(abs(r[0] - (x - d / 2)) < 1e-3 and abs(r[1] - (y - d / 2)) < 1e-3
               and abs(r[2] - r[0] - d) < 1e-3 and abs(r[3] - r[1] - d) < 1e-3
               for x, y in I.bezel_screws(lay))


def _inner_rects(wp, lay):
    """The bezel's window and cut-out outlines (the screw holes left out)."""
    return [r for r in _inner_wires(wp) if not _is_screw_hole(r, lay)]


def _has_rect(rects, want):
    return any(all(abs(a - b) < 1e-4 for a, b in zip(r, want)) for r in rects)


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_bezel_is_one_valid_solid(lay, key):
    _one_valid_solid(I.monitor_bezel(MONITORS[key], lay))


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_bezel_window_is_the_verify_rule_window(lay, key):
    m = MONITORS[key]
    wp = I.monitor_bezel(m, lay)
    rects = _inner_rects(wp, lay)
    want = _panel_rect_in_lid(m, lay, C.monitor_window(m))
    assert _has_rect(rects, want), (rects, want)
    w, h, _, _ = C.monitor_window(m)
    assert want[2] - want[0] == pytest.approx(w) and want[3] - want[1] == pytest.approx(h)


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_bezel_button_cutout(lay, key):
    m = MONITORS[key]
    rects = _inner_rects(I.monitor_bezel(m, lay), lay)
    cut = C.button_cutout(m)
    assert len(rects) == (1 if cut is None else 2)
    if cut is not None:
        assert _has_rect(rects, _panel_rect_in_lid(m, lay, cut))


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_bezel_covers_pocket_and_gutters(lay, key):
    """The bezel drops into the lid's opening (FIT each side) and spans the
    pocket and every cable gutter, so no cable shows round the picture."""
    bb = I.monitor_bezel(MONITORS[key], lay).val().BoundingBox()
    x0, y0, x1, y1 = _opening(lay)
    for b in [lay.lid_pocket, *lay.lid_cable_gutters.values()]:
        assert bb.xmin <= b.x0 + L.FIT + EPS and bb.xmax >= b.x1 - L.FIT - EPS
        assert bb.ymin <= b.y0 + L.FIT + EPS and bb.ymax >= b.y1 - L.FIT - EPS
    # ... and inside the opening, with FIT
    assert bb.xmin >= x0 + L.FIT - EPS and bb.xmax <= x1 - L.FIT + EPS
    assert bb.ymin >= y0 + L.FIT - EPS and bb.ymax <= y1 - L.FIT + EPS
    assert bb.zmin == pytest.approx(0.0) and bb.zmax == pytest.approx(L.INSERT_MATERIAL)
    # one plate over the whole opening: its area is the opening less the holes
    s = I.monitor_bezel(MONITORS[key], lay).val()
    area = s.Volume() / L.INSERT_MATERIAL
    holes = sum((r[2] - r[0]) * (r[3] - r[1]) for r in _inner_rects(I.monitor_bezel(
        MONITORS[key], lay), lay))
    screws = len(I.bezel_screws(lay)) * math.pi * (I.BEZEL_SCREW_D / 2) ** 2
    plate = _box(bb.xmin, bb.ymin, 0.0, bb.xmax, bb.ymax, L.INSERT_MATERIAL)
    relief = sum(plate.intersect(r).Volume() for r in H.knuckle_relief(lay, (0.0, 0.0)))
    assert relief > 0
    assert area + holes + screws + relief / L.INSERT_MATERIAL == pytest.approx(
        (bb.xmax - bb.xmin) * (bb.ymax - bb.ymin), rel=1e-5)


def test_bezel_clears_the_base_knuckles(lay):
    """Closed, the base knuckles sit in the lid's corner by the axis, where
    the bezel's hinge edge is: it is relieved round them."""
    knuckles = H.hinge_base_knuckles(lay).val().moved(lay.lid_location(0.0).inverse)
    for m in MONITORS.values():
        assert _common(I.monitor_bezel(m, lay).val(), knuckles) <= VOL_TOL


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_bezel_has_its_screw_holes(lay, key):
    """R15: a clearance hole at each bezel_screws corner, and every corner of
    the opening that is a cable-gutter corner has one."""
    wires = _inner_wires(I.monitor_bezel(MONITORS[key], lay))
    screws = I.bezel_screws(lay)
    assert len(screws) >= 3
    assert sum(_is_screw_hole(r, lay) for r in wires) == len(screws)
    p = lay.lid_pocket
    for x, y in screws:   # never in the pocket, where the panel is
        assert not (p.x0 <= x <= p.x1 and p.y0 <= y <= p.y1)


# --- monitor retainer ------------------------------------------------------------------

@pytest.mark.parametrize("key", sorted(MONITORS))
def test_retainer_is_one_valid_solid(lay, key):
    _one_valid_solid(I.monitor_retainer(MONITORS[key], lay))


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_retainer_in_the_pocket_behind_the_bezel_clear_of_the_panel(lay, key):
    m = MONITORS[key]
    s = I.monitor_retainer(m, lay).val()
    bb = s.BoundingBox()
    p = lay.lid_pocket
    assert bb.xmin >= p.x0 + L.FIT - EPS and bb.xmax <= p.x1 - L.FIT + EPS
    assert bb.ymin >= p.y0 + L.FIT - EPS and bb.ymax <= p.y1 - L.FIT + EPS
    assert bb.zmin == pytest.approx(L.INSERT_MATERIAL)
    assert bb.zmax == pytest.approx(L.insert_stack(m))
    assert bb.zmax <= p.z1 - L.FIT + EPS
    pb = C.panel_in_lid(m, lay)
    assert _common(s, _box(pb.x0, pb.y0, pb.z0, pb.x1, pb.y1, pb.z1)) <= VOL_TOL
    # the walls locate the panel: they touch it
    assert _dist(s, _box(pb.x0, pb.y0, pb.z0, pb.x1, pb.y1, pb.z1)) < TOUCH


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_retainer_leaves_the_cable_exit_open(lay, key):
    """Along the exit edge the retainer's wall has a cable slot: a probe just
    outside the middle of that edge, through the panel's thickness, is clear."""
    m = MONITORS[key]
    s = I.monitor_retainer(m, lay).val()
    pb = C.panel_in_lid(m, lay)
    edge = L.exit_edge(m)
    cx, cy = (pb.x0 + pb.x1) / 2, (pb.y0 + pb.y1) / 2
    d = 2 * L.INSERT_MATERIAL
    probe = {"bottom": (cx - 5, pb.y1, cx + 5, pb.y1 + d),
             "top": (cx - 5, pb.y0 - d, cx + 5, pb.y0),
             "right": (pb.x1, cy - 5, pb.x1 + d, cy + 5),
             "left": (pb.x0 - d, cy - 5, pb.x0, cy + 5)}[edge]
    x0, y0, x1, y1 = probe
    assert _common(s, _box(x0, y0, pb.z0, x1, y1, pb.z1)) <= VOL_TOL


def test_kit_retainer_holds_the_driver_on_standoffs(lay):
    kits = [m for m in MONITORS.values() if m.driver is not None]
    assert kits
    for m in kits:
        s = I.monitor_retainer(m, lay).val()
        pb = C.panel_in_lid(m, lay)
        pcb_z = pb.z1 + L.DRIVER_STANDOFF       # driver PCB's panel-side face
        env = I.driver_envelope(m, lay)
        assert env.z0 == pytest.approx(pcb_z)
        assert env.z1 == pytest.approx(L.insert_stack(m) - L.INSERT_MATERIAL)
        posts = I.driver_posts(m, lay)
        assert len(posts) == len(m.driver_holes) == 4
        for p in posts:
            assert p.z0 == pytest.approx(pb.z1) and p.z1 == pytest.approx(pcb_z)
            assert env.x0 < p.cx < env.x1 and env.y0 < p.cy < env.y1
            assert p.r - I.COUNTERBORE_D / 2 >= C.MIN_BOSS_WALL - EPS
            # the post's top carries the PCB; screw clearance and head
            # counterbore are empty
            top = cq.Solid.makeCylinder(p.r - 0.1, 0.2, cq.Vector(p.cx, p.cy, p.z1 - 0.2))
            shank = cq.Solid.makeCylinder(1.5, p.z1 - p.z0, cq.Vector(p.cx, p.cy, p.z0))
            head = cq.Solid.makeCylinder(2.75, I.COUNTERBORE_H, cq.Vector(p.cx, p.cy, p.z0))
            assert _common(s, top) > 0
            assert _common(s, shank) <= VOL_TOL
            assert _common(s, head) <= VOL_TOL
        # nothing of the retainer in the board's envelope; the posts reach it
        e = _box(env.x0, env.y0, env.z0, env.x1, env.y1, env.z1)
        assert _common(s, e) <= VOL_TOL
        assert _dist(s, e) < TOUCH
        n = I.driver_screw_length(m)
        assert n in m3.LENGTHS
        assert n >= (L.DRIVER_STANDOFF - I.COUNTERBORE_H + m.driver_pcb_t + H.NYLOC_H
                     + H.THREAD_PAST)


def test_cased_retainer_has_no_posts(lay):
    for m in MONITORS.values():
        if m.driver is None:
            assert I.driver_posts(m, lay) == ()


# --- battery packing -----------------------------------------------------------------

def _bank_box(b, lay):
    L_, W_, H_ = b.size
    cy = (lay.bay.y0 + lay.bay.y1) / 2
    return _box(lay.bay.x0, cy - W_ / 2, lay.bay.z0, lay.bay.x0 + L_, cy + W_ / 2,
                lay.bay.z0 + H_)


@pytest.mark.parametrize("key", sorted(BATTERIES))
def test_packing_is_one_valid_solid(lay, key):
    _one_valid_solid(P.battery_packing(BATTERIES[key], lay))


@pytest.mark.parametrize("key", sorted(BATTERIES))
def test_packing_plus_battery_is_bay_less_fit(lay, key):
    b = BATTERIES[key]
    s = P.battery_packing(b, lay).val()
    bay = lay.bay
    cy = (bay.y0 + bay.y1) / 2
    # the end-stop: what of the packing lies on the bay's centre line
    line = _box(bay.x0, cy - 0.5, bay.z0, bay.x1, cy + 0.5, bay.z0 + 1.0)
    stop = s.intersect(line).BoundingBox()
    end_stop = stop.xmax - stop.xmin
    assert end_stop + b.size[0] == pytest.approx(bay.size[0] - L.FIT)
    assert stop.xmax == pytest.approx(bay.x1)


@pytest.mark.parametrize("key", sorted(BATTERIES))
def test_packing_u_spacer_holds_the_bank_with_fit(lay, key):
    b = BATTERIES[key]
    s = P.battery_packing(b, lay).val()
    bank = _bank_box(b, lay)
    bb = s.BoundingBox()
    bay = lay.bay
    assert bb.xmin >= bay.x0 - EPS and bb.xmax <= bay.x1 + EPS
    assert bb.ymin == pytest.approx(bay.y0) and bb.ymax == pytest.approx(bay.y1)
    assert bb.zmin == pytest.approx(bay.z0) and bb.zmax <= bay.z1 + EPS
    assert _common(s, bank) <= VOL_TOL
    assert _dist(s, bank) == pytest.approx(L.FIT)
    # side arms on both sides of the bank, along its length
    cx = bay.x0 + b.size[0] / 2
    for y0, y1 in ((bay.y0, bank.BoundingBox().ymin), (bank.BoundingBox().ymax, bay.y1)):
        assert _common(s, _box(cx - 1, y0, bay.z0, cx + 1, y1, bay.z0 + 1)) > 0


@pytest.mark.parametrize("key", sorted(BATTERIES))
def test_packing_engraved_with_the_model_name(lay, key):
    b = BATTERIES[key]
    s = P.battery_packing(b, lay).val()
    L_, W_, H_ = b.size
    bay = lay.bay
    # the plain U: the bay footprint less the bank's slot (bank + FIT round it)
    plain = H_ * (bay.size[0] * bay.size[1] - (L_ + L.FIT) * (W_ + 2 * L.FIT))
    assert s.Volume() < plain - 1.0
    assert s.BoundingBox().zmax == pytest.approx(bay.z0 + H_)
    assert P.engraving(b) == b.key


# --- MT1 locating pin ----------------------------------------------------------------

def test_locating_pin_is_one_valid_solid_of_peg_dia(lay):
    s = _one_valid_solid(pin.locating_pin(lay))
    bb = s.BoundingBox()
    assert bb.xmax - bb.xmin == pytest.approx(L.PEG_DIA)
    assert bb.ymax - bb.ymin == pytest.approx(L.PEG_DIA)
    # from the deck (the bottom of the boss's through hole) to the peg's top
    peg = next(iter(lay.pegs.values()))
    assert bb.zmax - bb.zmin == pytest.approx(peg.z1 - lay.mt1_boss.z0)
    assert all(p.z1 == peg.z1 and p.r == L.PEG_DIA / 2 for p in lay.pegs.values())
    assert math.isclose(s.Volume(), math.pi * (L.PEG_DIA / 2) ** 2 * (bb.zmax - bb.zmin),
                        rel_tol=0.05)



def test_verify_reports_the_driver_placeholders(capsys):
    import verify
    assert verify.main() == 0
    out = capsys.readouterr().out
    assert "driver PCB thickness, face and mounting holes" in out
