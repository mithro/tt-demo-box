"""The shared layout: every placement derived from the part data, both walls."""

import math

import pytest
from shapely import Point

from demobox import layout as L
from demobox.geom import Box, box_gap
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import BOARD_KEYS, board_spec
from demobox.parts.monitors import MONITORS

WALLS = (2.4, 3.0)


@pytest.fixture(params=WALLS, ids=lambda w: f"wall{w}")
def lay(request):
    return L.layout(request.param)


def _inside(inner: Box, outer: Box, margin: float) -> bool:
    return (inner.x0 >= outer.x0 + margin - 1e-9 and inner.x1 <= outer.x1 - margin + 1e-9
            and inner.y0 >= outer.y0 + margin - 1e-9 and inner.y1 <= outer.y1 - margin + 1e-9)


def test_spec_constants():
    assert L.LID_OPEN_DEG == 100.0
    assert L.BAY_INSIDE == (158.0, 82.0, 34.0)
    assert L.CABLE_BAY == 35.0
    assert L.LID_POCKET_MIN == (185.0, 120.0)
    assert L.FIT == 0.5
    assert L.CLOSED_CLEARANCE == 2.0


def test_bay_size_and_drawer_slides_out_along_minus_x(lay):
    assert lay.bay.size == pytest.approx(L.BAY_INSIDE)
    assert lay.drawer_out == (-1.0, 0.0, 0.0)
    # cable bay at the drawer-face (-X) end of the bay, same section
    assert lay.cable_bay.size[0] == pytest.approx(L.CABLE_BAY)
    assert lay.cable_bay.x1 == pytest.approx(lay.bay.x0)
    assert lay.cable_bay.size[1:] == pytest.approx(lay.bay.size[1:])
    # the drawer face is the base's left (-X) outside face
    assert lay.drawer_face_hole.x0 == pytest.approx(lay.outer.x0)
    assert lay.drawer_face_hole.size[0] == pytest.approx(lay.wall)
    # bay and cable bay inside the base walls, with slide clearance
    for b in (lay.bay, lay.cable_bay):
        assert b.y0 >= lay.outer.y0 + 2 * lay.wall + L.FIT - 1e-9
        assert b.y1 <= lay.outer.y1 - 2 * lay.wall - L.FIT + 1e-9
        assert b.z0 >= lay.outer.z0 and b.z1 < lay.deck_z
    # the drawer sets the width: back wall, slide clearance, base wall, nothing more
    assert lay.outer.x1 == pytest.approx(lay.bay.x1 + lay.wall + L.FIT + lay.wall)


def test_drawer_travel_lets_every_bank_lift_out(lay):
    longest = max(b.size[0] for b in BATTERIES.values())
    # bank's port end sits at the cable-bay boundary; after the travel the
    # whole bank is outside the base's left face
    assert lay.bay.x0 + longest - lay.drawer_travel <= lay.outer.x0 - L.FIT + 1e-9
    # the drawer's back wall is still inside the base (it is not pulled off)
    assert lay.bay.x1 + lay.wall - lay.drawer_travel > lay.outer.x0 + lay.wall


def test_drawer_face_hole_covers_end_buttons(lay):
    h = lay.drawer_face_hole
    for b in BATTERIES.values():
        if b.button is None or b.button[0] != "end":
            continue
        _, u, v = b.button
        y = lay.bay.y0 + (lay.bay.size[1] - b.size[1]) / 2 + u
        z = lay.bay.z0 + v
        assert h.y0 < y < h.y1 and h.z0 < z < h.z1, b.key


def test_envelopes_on_the_deck_inside_walls(lay):
    for key in BOARD_KEYS:
        for part in ("envelope", "usb_plug", "tinyvga"):
            k = lay.board_keepouts[f"{key}/{part}"]
            assert _inside(k, lay.outer, lay.wall + L.FIT), (key, part, k)
            assert k.z1 <= lay.outer.z1 - L.CLOSED_CLEARANCE + 1e-9
        env = lay.board_keepouts[f"{key}/envelope"]
        assert env.z0 >= lay.deck_z
        assert env.z0 == pytest.approx(lay.board_origin[2])


def test_board_placed_rotated_not_mirrored(lay):
    """Component side up, Pmod edge (board y = 0) towards the hinge."""
    ox, oy, _ = lay.board_origin
    for key in BOARD_KEYS:
        spec = board_spec(key)
        env = lay.board_keepouts[f"{key}/envelope"]
        # Pmod edge at base Y = oy, the board towards the visitor (-Y)
        assert env.y1 == pytest.approx(oy - min(p.body_y0 for p in spec.pmods))
        assert env.y0 < oy
        # board x maps to -X: a 180 degree turn about Z (det +1), not a mirror
        assert env.x1 == pytest.approx(ox)
        assert env.x0 == pytest.approx(ox - spec.outline.width)
    # J1 lands front-left of the board
    j1 = lay.board_keepouts["v3.2/usb_plug"]
    env = lay.board_keepouts["v3.2/envelope"]
    assert (j1.x0 + j1.x1) / 2 < (env.x0 + env.x1) / 2
    assert j1.y1 <= env.y0 + 1e-9


def test_standoffs_at_holes(lay):
    ox, oy, oz = lay.board_origin
    centres = [(round(s.cx, 6), round(s.cy, 6)) for s in lay.standoffs]
    assert len(centres) == len(set(centres))
    for s in lay.standoffs:
        assert s.z0 == pytest.approx(lay.deck_z) and s.z1 == pytest.approx(oz)

    def at(key, label):
        h = next(h for h in board_spec(key).holes if h.label == label)
        return (round(ox - h.x, 6), round(oy - h.y, 6))

    assert at("v3.2", "MT2") == at("v3.3", "MT2")
    for key in BOARD_KEYS:
        assert at(key, "MT1") in centres
        assert at(key, "MT2") in centres
    # plus edge supports, so two holes do not let the board rock
    assert len(lay.standoffs) >= 5


def test_usb_slot_under_each_j1_plug(lay):
    s = lay.usb_slot
    assert s.z1 == pytest.approx(lay.deck_z)
    assert s.size[2] == pytest.approx(lay.wall)
    for key in BOARD_KEYS:
        p = lay.board_keepouts[f"{key}/usb_plug"]
        assert s.x0 < p.x0 and s.x1 > p.x1        # plug width fits through
        assert s.y0 < p.y0 < s.y1                # the plug's cable end is over it
        assert s.z1 <= p.z0


def test_tinyvga_behind_board_below_hinge(lay):
    hy, hz = lay.hinge_axis
    for key in BOARD_KEYS:
        v = lay.board_keepouts[f"{key}/tinyvga"]
        env = lay.board_keepouts[f"{key}/envelope"]
        assert v.y0 >= env.y1 - 1e-9          # behind the board (larger Y)
        assert v.z1 < hz                      # below the hinge axis
        assert v.y1 <= hy


def test_plug_choice_is_justified():
    # the straight plug would overflow the 220 mm print bed with the printed walls
    assert L.VGA_PLUG_STRAIGHT is False
    assert L._base_depth(2.4, straight=True) > L.PRINT_BED[1]
    assert L._base_depth(2.4, straight=False) <= L.PRINT_BED[1]
    assert L.layout(2.4).outer.size[1] == pytest.approx(L._base_depth(2.4, straight=False))


def test_base_fits_print_bed():
    o = L.layout(2.4).outer
    assert o.size[0] <= L.PRINT_BED[0] and o.size[1] <= L.PRINT_BED[1]


def test_lid_pocket(lay):
    px, py, pz = lay.lid_pocket.size
    assert px >= L.LID_POCKET_MIN[0] and py >= L.LID_POCKET_MIN[1]
    for m in MONITORS.values():
        w, h, _ = m.panel
        assert px >= w + 2 * L.INSERT_MATERIAL + 2 * L.FIT - 1e-9
        assert py >= h + 2 * L.INSERT_MATERIAL + 2 * L.FIT - 1e-9
    # the pocket lies inside the lid, open on the screen (z = 0) face
    o = lay.lid_outer
    assert _inside(lay.lid_pocket, o, lay.wall)
    assert lay.lid_pocket.z0 == pytest.approx(o.z0)
    assert lay.lid_pocket.z1 == pytest.approx(o.z1 - lay.wall)
    # lid frame: origin on the hinge axis, lid in front of (-Y) and above it closed
    assert o.y1 == pytest.approx(0.0) and o.z0 == pytest.approx(0.0)
    assert o.size[1] == pytest.approx(lay.outer.size[1])
    assert (o.x0, o.x1) == pytest.approx((lay.outer.x0, lay.outer.x1))


def test_lid_depth_holds_deepest_stack(lay):
    for m in MONITORS.values():
        assert lay.lid_pocket.size[2] >= L.insert_stack(m) + L.FIT - 1e-9


def test_hinge_axis_at_back_top(lay):
    hy, hz = lay.hinge_axis
    assert hy == pytest.approx(lay.outer.y1)
    assert hz == pytest.approx(lay.outer.z1)


def test_hinge_cable_channel(lay):
    c = lay.hinge_cable_channel
    hy, hz = lay.hinge_axis
    assert c.y0 < hy <= c.y1 + 1e-9 and c.z0 < hz < c.z1
    v = lay.board_keepouts["v3.2/tinyvga"]
    assert c.x0 <= (v.x0 + v.x1) / 2 <= c.x1


def test_boost_pocket_inside_base_below_deck(lay):
    b = lay.boost_pocket
    assert _inside(b, lay.outer, lay.wall)
    assert b.z1 <= lay.deck_z - lay.wall + 1e-9
    for d in (lay.bay, lay.cable_bay):
        assert box_gap(b, d) > 0


def test_lid_profile_rotates_about_hinge(lay):
    hy, hz = lay.hinge_axis
    o = lay.lid_outer
    closed = lay.lid_profile_yz(0.0)
    minx, miny, maxx, maxy = closed.bounds
    assert (minx, miny, maxx, maxy) == pytest.approx((hy + o.y0, hz, hy, hz + o.z1))
    open_ = lay.lid_profile_yz(L.LID_OPEN_DEG)
    # open: the front edge has swung up and just past vertical, behind the axis
    front = (hy + o.y0 * math.cos(math.radians(L.LID_OPEN_DEG)),
             hz - o.y0 * math.sin(math.radians(L.LID_OPEN_DEG)))
    assert front[0] > hy and front[1] > hz + 0.9 * o.size[1]
    assert open_.area == pytest.approx(closed.area)
    assert open_.exterior.distance(Point(front)) < 1e-6


def test_lid_location_matches_profile(lay):
    import cadquery as cq
    o = lay.lid_outer
    for ang in (0.0, 45.0, L.LID_OPEN_DEG):
        loc = lay.lid_location(ang)
        poly = lay.lid_profile_yz(ang)
        for (y, z) in ((o.y0, o.z0), (o.y0, o.z1), (o.y1, o.z1)):
            p = cq.Vertex.makeVertex(10.0, y, z).moved(loc).Center()
            assert p.x == pytest.approx(10.0)
            assert poly.exterior.distance(Point(p.y, p.z)) < 1e-6
