"""The compact layout: every placement derived from the part data, both routes."""

import math

import pytest
from shapely import Point

from demobox import layout as L
from demobox.geom import Box, box_gap
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import BOARD_KEYS, board_envelope, board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS
from demobox.parts.tinyvga import TINYVGA

ROUTES = sorted(L.ROUTES)
EPS = 1e-9


@pytest.fixture(params=ROUTES)
def lay(request):
    return L.layout(L.ROUTES[request.param])


def _inside(inner: Box, outer: Box, margin: float = 0.0) -> bool:
    return (inner.x0 >= outer.x0 + margin - EPS and inner.x1 <= outer.x1 - margin + EPS
            and inner.y0 >= outer.y0 + margin - EPS and inner.y1 <= outer.y1 - margin + EPS
            and inner.z0 >= outer.z0 - EPS and inner.z1 <= outer.z1 + EPS)


def _xy_overlap(a: Box, b: Box) -> bool:
    return a.x0 < b.x1 - EPS and b.x0 < a.x1 - EPS and a.y0 < b.y1 - EPS and b.y0 < a.y1 - EPS


def _to_base(lay, x, y, z=0.0):
    """The documented board-to-base turn: base = (ox - by, oy + bx, oz + bz)."""
    ox, oy, oz = lay.board_origin
    return (ox - y, oy + x, oz + z)


def _board_row_board_frame(adapter: bool) -> tuple[float, float, float, float, float, float]:
    """(x0, x1, y0, y1, z0, z1) of both revisions' keep-outs, board frame, from
    the part data (not from the layout)."""
    usb = CABLES["usb-c-right-angle"].plug
    xs, ys, zs = [], [], []
    for k in BOARD_KEYS:
        env = board_envelope(k)
        j1 = next(f for f in board_spec(k).features if f.kind == "usb_power")
        dx, dy, dz = L.tinyvga_offset(k)
        vga = TINYVGA.pcb.union(TINYVGA.de15).union(TINYVGA.plug_keepout(not adapter))
        xs += [env.x0, env.x1, vga.x0 + dx, vga.x1 + dx]
        ys += [env.y0, env.y1, j1.y1 + usb[0], vga.y0 + dy, vga.y1 + dy]
        axis = board_spec(k).outline.thickness + L.USB_C_AXIS_ABOVE_PCB
        zs += [env.z0, env.z1, axis - usb[2] / 2, axis + usb[2] / 2, vga.z0 + dz, vga.z1 + dz]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


# --- constants ---------------------------------------------------------------------

def test_spec_constants():
    assert L.LID_OPEN_DEG == 100.0
    assert L.PRINT_BED == (220.0, 220.0) and L.LASER_BED == (300.0, 200.0)
    assert L.ROUTES == {"printed": 2.4, "laser": 3.0}
    assert L.SLACK == 1.0 and L.FIT == 0.5 and L.CLOSED_CLEARANCE == 2.0
    assert L.DESIGN_MONITOR == "taobao-tim" and L.DESIGN_BANK == "xiaomi-pb2020"
    assert L.PIN_ROD_D == 3.0 and L.PIN_PROUD == L.CLOSED_CLEARANCE + L.SLACK + 1.0
    assert L.FINGERTIP_D == 16.0 and L.KNUCKLE_R == 4.0
    assert L.BANK_SIDE_PLUGS == ("usb-c-right-angle", "usb-a-c", "bank-built-in")
    assert L.MAGNET_D == 6.0 and L.MAGNET_T == 3.0


def test_removed_names_are_gone():
    for name in ("BAY_INSIDE", "CABLE_BAY", "LID_POCKET_MIN", "HEATSET_HOLE_D", "HEATSET_DEPTH",
                 "INSERT_MATERIAL", "DRIVER_STANDOFF", "STANDOFF_MIN", "FINGER_HOLE_D",
                 "CATCH_INSET_X", "insert_stack", "_pocket_xy", "_gutter_widths",
                 "lid_cable_bundle", "_drawer_depth", "_finger_slot"):
        assert not hasattr(L, name), name


def test_unconfirmed_lists_tape():
    assert "TAPE_T" in {name for name, _, _ in L.UNCONFIRMED}
    assert dict((n, v) for n, v, _ in L.UNCONFIRMED)["TAPE_T"] == L.TAPE_T == 1.0


# --- size budget (R5) ----------------------------------------------------------------

def test_size_budget(lay):
    w, s = lay.wall, L.SLACK
    bank = BATTERIES[L.DESIGN_BANK]
    panel = MONITORS[L.DESIGN_MONITOR].panel

    rows = {a: _board_row_board_frame(a) for a in (False, True)}
    row_len = {a: r[3] - r[2] for a, r in rows.items()}     # board y runs along base X
    adapter = row_len[True] < row_len[False]
    assert lay.vga_adapter is adapter
    x0, x1, _, _, z0, z1 = rows[adapter]
    board_row_x = row_len[adapter] + 2 * s
    board_row_y = x1 - x0
    stack_h = z1 - z0

    port = max(max(CABLES[k].plug[0] for k in L.BANK_SIDE_PLUGS) + s, L.FINGERTIP_D)
    bank_row_x = port + bank.size[0] + 2 * s
    bank_row_y = bank.size[1] + 2 * s
    # R10: the boost goes at the bank row's +X end, along X or turned, if
    # either fits the width the other rows set; else in the lid
    bl, bw, bh = (d + 2 * s for d in CABLES["usb-12v-boost"].plug)
    room = max(board_row_x, panel[0] + 2 * s) - bank_row_x
    fits = [(fx, fy) for fx, fy in ((bl, bw), (bw, bl))
            if fx <= room and fy <= bank_row_y and bh <= lay.rim_z - w]
    assert lay.boost_in_lid is (not fits)
    if fits:
        assert lay.boost_pocket.size[:2] == pytest.approx(fits[0])
        bank_row_x += fits[0][0]

    width = max(board_row_x, bank_row_x, panel[0] + 2 * s) + 2 * w
    depth = max(w + s + board_row_y + s + bank_row_y + s + w, panel[1] + 2 * s + 2 * w)
    rim = w + max(bank.size[2], stack_h) + s
    assert lay.outer == Box(0.0, 0.0, 0.0, width, depth, rim, lay.outer.what)
    assert lay.outer.size == pytest.approx((width, depth, rim))
    assert lay.rim_z == pytest.approx(rim)
    assert lay.lid_outer.size[2] == pytest.approx(w + L.TAPE_T + panel[2] + L.CLOSED_CLEARANCE)


def test_size_budget_printed_literals():
    """R5: the printed design kit, derived by hand from the part data.

    Board row, board frame (both revisions' keep-outs):
      board y (base X): v3.3 J1 shell y1 86.65 + USB-C plug 20.0 = 106.65;
        TinyVGA plug end: pmod3 body_y0 -8.55 + DE-15 face -51.25
        - (plug body 17.0 + 90 degree run 20.0) = -96.8  (straight: -116.8)
        -> 203.45 with the adapter, 223.45 straight: vga_adapter = True.
      board x (base Y): PCB 0 .. TinyVGA x1 (56.855 + 33.0) = 89.855.
      z: TinyVGA plug hood 1.6 + 12.5/2 - 20/2 = -2.15 .. 1.6 + 6.25 + 10 = 17.85 -> 20.0.
    Width  = max(203.45 + 2*1 = 205.45, bank row 23 + 128 + 2 + 22 = 175, panel 182 + 2 = 184)
             + 2*2.4 = 210.25   (board row wins).
             port room = max(max(20, 22, 20) + 1, 16) = 23.
             boost (60 x 20 x 15 + 2*1): along X 153 + 62 = 215 > 205.45, so it is turned:
             X 22 (153 + 22 = 175 <= 205.45), Y 62 <= bank row 75, Z 17 -> in the base.
    Depth  = 2.4 + 1 + 89.855 + 1 + (73 + 2) + 1 + 2.4 = 172.655   (>= 118 + 2 + 4.8 = 124.8)
    Rim    = 2.4 + max(bank 32, board stack 20.0) + 1 = 35.4        (bank wins)
    Lid    = 2.4 + tape 1.0 + monitor 20.0 + clearance 2.0 = 25.4
    """
    lay = L.layout(L.ROUTES["printed"])
    assert lay.vga_adapter is True and lay.boost_in_lid is False
    assert lay.boost_pocket.size == pytest.approx((22.0, 62.0, 17.0), abs=0.01)
    assert lay.outer.size == pytest.approx((210.25, 172.655, 35.4), abs=0.01)
    assert lay.lid_outer.size == pytest.approx((210.25, 172.655, 25.4), abs=0.01)
    assert lay.port_room.size[0] == pytest.approx(23.0, abs=0.01)


# --- arrangement -------------------------------------------------------------------

def _board_row(lay) -> Box:
    ks = list(lay.board_keepouts.values())
    u = ks[0]
    for k in ks[1:]:
        u = u.union(k)
    return u


def test_long_edges_along_x(lay):
    row = _board_row(lay)
    assert row.size[0] > row.size[1]
    assert lay.bank_bay.size[0] > lay.bank_bay.size[1]


def test_board_row_front_bank_row_behind(lay):
    row = _board_row(lay)
    w, s = lay.wall, L.SLACK
    assert row.y0 == pytest.approx(w + s)
    assert row.x0 == pytest.approx(w + s)
    assert lay.bank_bay.y0 == pytest.approx(row.y1 + s)
    assert lay.port_room.y0 == pytest.approx(lay.bank_bay.y0)
    assert lay.port_room.x0 == pytest.approx(w)
    assert lay.bank_bay.x0 == pytest.approx(lay.port_room.x1)
    for b in (lay.bank_bay, lay.port_room):
        assert b.z0 == pytest.approx(w) and b.z1 == pytest.approx(lay.rim_z)
        assert _inside(b, lay.outer, w)
    assert _inside(row, lay.outer, w + s)


def test_board_top_level_with_rim(lay):
    assert max(b.z1 for b in lay.board_keepouts.values()) == pytest.approx(lay.rim_z - L.SLACK)
    # the plinth carries the PCB underside, from the floor
    p = lay.plinth
    assert p.z0 == pytest.approx(lay.wall) and p.z1 == pytest.approx(lay.board_origin[2])
    for k in BOARD_KEYS:
        assert lay.board_keepouts[f"{k}/envelope"].z0 == pytest.approx(p.z1)


def _pcb_union_base(lay) -> Box:
    xs, ys = [], []
    for k in BOARD_KEYS:
        o = board_spec(k).outline
        for x in (0.0, o.width):
            for y in (0.0, o.height):
                bx, by, _ = _to_base(lay, x, y)
                xs.append(bx)
                ys.append(by)
    return Box(min(xs), min(ys), 0.0, max(xs), max(ys), 0.0)


def test_plinth_covers_both_pcb_outlines(lay):
    """R7: the plinth is the union of both revisions' PCB outlines."""
    p, u = lay.plinth, _pcb_union_base(lay)
    assert (p.x0, p.y0, p.x1, p.y1) == pytest.approx((u.x0, u.y0, u.x1, u.y1))


def test_plinth_relief_takes_the_hanging_j1_plug(lay):
    """R7: the relief holds the v3.2 J1 plug's part below the PCB underside,
    with FIT round it; the TinyVGA is past the plinth altogether."""
    oz = lay.board_origin[2]
    r, p = lay.plinth_relief, lay.plinth
    plug = lay.board_keepouts["v3.2/usb_plug"]
    assert plug.z0 < oz and _xy_overlap(plug, p)      # it would hit the plinth
    below = Box(plug.x0, plug.y0, plug.z0, plug.x1, plug.y1, oz)
    assert _inside(below, r)
    assert r.x0 == pytest.approx(plug.x0 - L.FIT) and r.x1 == pytest.approx(plug.x1 + L.FIT)
    assert r.y0 == pytest.approx(plug.y0 - L.FIT) and r.y1 == pytest.approx(plug.y1 + L.FIT)
    assert r.z1 == pytest.approx(p.z1)
    assert r.z0 == pytest.approx(plug.z0 - L.FIT)
    for k in BOARD_KEYS:
        assert not _xy_overlap(p, lay.board_keepouts[f"{k}/tinyvga"])
        other = lay.board_keepouts[f"{k}/usb_plug"]
        if _xy_overlap(p, other):
            assert _inside(Box(other.x0, other.y0, other.z0, other.x1, other.y1, oz), r), k


def test_pin_holes_inside_the_plinth(lay):
    """R7: every pin hole is inside the plinth, at least 1.5 mm from each
    plinth edge and from the relief."""
    p, r = lay.plinth, lay.plinth_relief
    rh = L.PEG_HOLE_D / 2
    for key, pin in lay.pins.items():
        edges = (pin.cx - p.x0, p.x1 - pin.cx, pin.cy - p.y0, p.y1 - pin.cy)
        assert min(edges) - rh >= 1.5 - EPS, (key, edges)
        dx = max(r.x0 - pin.cx, pin.cx - r.x1, 0.0)
        dy = max(r.y0 - pin.cy, pin.cy - r.y1, 0.0)
        assert math.hypot(dx, dy) - rh >= 1.5 - EPS, key


def test_board_cannot_leave_pins(lay):
    """R8: closed, the board (with its TinyVGA and plug) can lift at most to
    the monitor face; at least 1 mm of every pin stays in its hole."""
    hz = lay.hinge_axis[1]
    face = hz + lay.monitor_space.z0
    top = max(b.z1 for b in lay.board_keepouts.values())
    assert face - top <= L.PIN_PROUD - 1.0 + EPS


def test_board_turn_is_a_rotation_not_a_mirror(lay):
    """base = (ox - by, oy + bx, oz + bz): +90 degrees about Z."""
    o = _to_base(lay, 0.0, 0.0)
    ex = _to_base(lay, 1.0, 0.0)
    ey = _to_base(lay, 0.0, 1.0)
    ux = (ex[0] - o[0], ex[1] - o[1])
    uy = (ey[0] - o[0], ey[1] - o[1])
    assert ux == pytest.approx((0.0, 1.0)) and uy == pytest.approx((-1.0, 0.0))
    assert ux[0] * uy[1] - ux[1] * uy[0] == pytest.approx(1.0)   # det +1: not mirrored
    assert _to_base(lay, 0.0, 0.0, 1.0)[2] - o[2] == pytest.approx(1.0)   # component side up
    for k in BOARD_KEYS:
        env = board_envelope(k)
        got = lay.board_keepouts[f"{k}/envelope"]
        corners = [_to_base(lay, x, y, z) for x in (env.x0, env.x1)
                   for y in (env.y0, env.y1) for z in (env.z0, env.z1)]
        assert (got.x0, got.y0, got.z0) == pytest.approx(tuple(min(c[i] for c in corners)
                                                               for i in range(3)))
        assert (got.x1, got.y1, got.z1) == pytest.approx(tuple(max(c[i] for c in corners)
                                                               for i in range(3)))


def test_j1_left_tinyvga_right(lay):
    plugs = [lay.board_keepouts[f"{k}/usb_plug"] for k in BOARD_KEYS]
    vgas = [lay.board_keepouts[f"{k}/tinyvga"] for k in BOARD_KEYS]
    assert max(p.x1 for p in plugs) < min(v.x0 for v in vgas)
    # J1 is by the port room, the Pmod edge at +X
    for k in BOARD_KEYS:
        j1 = next(f for f in board_spec(k).features if f.kind == "usb_power")
        x, _, _ = _to_base(lay, (j1.x0 + j1.x1) / 2, (j1.y0 + j1.y1) / 2)
        pmod_x, _, _ = _to_base(lay, 0.0, 0.0)
        assert x < pmod_x


def test_pins(lay):
    oz = lay.board_origin[2]
    assert set(lay.pins) == {"MT2"} | {f"{k}/MT1" for k in BOARD_KEYS}
    for k in BOARD_KEYS:
        spec = board_spec(k)
        top = oz + spec.outline.thickness
        holes = {h.label: h for h in spec.holes}
        for label, key in (("MT2", "MT2"), ("MT1", f"{k}/MT1")):
            h = holes[label]
            pin = lay.pins[key]
            x, y, _ = _to_base(lay, h.x, h.y)
            assert (pin.cx, pin.cy) == pytest.approx((x, y)), (k, key)
            assert pin.z1 == pytest.approx(top + L.PIN_PROUD), (k, key)
            assert pin.z0 == pytest.approx(lay.plinth.z1)
            assert 2 * pin.r == pytest.approx(L.PEG_DIA) and L.PEG_DIA < h.dia
            # on the plinth: the pin and its hole are inside the plinth top
            assert lay.plinth.x0 <= x <= lay.plinth.x1 and lay.plinth.y0 <= y <= lay.plinth.y1
    assert L.PEG_HOLE_D > L.PEG_DIA


def test_port_room_and_bank_bay(lay):
    bank = BATTERIES[L.DESIGN_BANK]
    s = L.SLACK
    pr = max(max(CABLES[k].plug[0] for k in L.BANK_SIDE_PLUGS) + s, L.FINGERTIP_D)
    assert lay.port_room.size[0] == pytest.approx(pr)
    assert lay.bank_bay.size[0] == pytest.approx(bank.size[0] + 2 * s)
    assert lay.bank_bay.size[1] == pytest.approx(bank.size[1] + 2 * s)
    assert lay.bank_bay.size[2] >= bank.size[2] + s - EPS
    # the port room is at -X, by J1
    j1 = min(lay.board_keepouts[f"{k}/usb_plug"].x0 for k in BOARD_KEYS)
    assert lay.port_room.x0 < j1 < lay.port_room.x1


@pytest.mark.parametrize("bank", sorted(BATTERIES))
def test_every_bank_as_design_bank(bank):
    for wall in L.ROUTES.values():
        ref = L.layout(wall)
        lay = L.layout(wall, bank=bank)
        b = BATTERIES[bank]
        assert lay.bank_bay.size[0] >= b.size[0] + 2 * L.SLACK - EPS
        assert lay.bank_bay.size[1] >= b.size[1] + 2 * L.SLACK - EPS
        assert lay.bank_bay.size[2] >= b.size[2] + L.SLACK - EPS
        xiaomi = BATTERIES[L.DESIGN_BANK].size
        for i in range(3):
            # R6: never larger than the Xiaomi box by more than the bank's own
            # excess over the Xiaomi (the Anker is 0.4 mm wider)
            excess = max(0.0, b.size[i] - xiaomi[i])
            assert lay.outer.size[i] <= ref.outer.size[i] + excess + EPS, (bank, wall, "xyz"[i])


def test_boost_pocket(lay):
    """R10: the design kit's boost module is in the base, turned, at the bank
    row's +X end, inside the walls and below the rim."""
    bl, bw, bh = (d + 2 * L.SLACK for d in CABLES["usb-12v-boost"].plug)
    p = lay.boost_pocket
    assert lay.boost_in_lid is False
    assert p.size == pytest.approx((bw, bl, bh))                 # turned 90 degrees
    assert p.x0 == pytest.approx(lay.bank_bay.x1)
    assert p.y0 == pytest.approx(lay.bank_bay.y0) and p.y1 <= lay.bank_bay.y1 + EPS
    assert p.z0 == pytest.approx(lay.wall) and p.z1 <= lay.rim_z + EPS
    assert _inside(p, lay.outer, lay.wall)


def test_huge_boost_goes_to_the_lid(monkeypatch):
    """A boost module too big for the bank row either way goes in the lid strip."""
    from dataclasses import replace
    monkeypatch.setattr(L, "_BOOST", replace(L._BOOST, plug=(100.0, 40.0, 10.0)))
    lay = L.layout(L.ROUTES["printed"])
    assert lay.boost_in_lid is True
    assert lay.boost_pocket.size == pytest.approx((102.0, 42.0, 12.0))
    assert _inside(lay.boost_pocket, lay.lid_strip)
    assert lay.outer.size[0] == pytest.approx(210.25)           # the box does not grow


def test_boost_in_the_bank_row_when_it_fits():
    """A short bank leaves room for the boost module beside it in the base."""
    lay = L.layout(L.ROUTES["printed"], bank="iniu-p512")
    assert lay.boost_in_lid is False
    assert lay.boost_pocket.y0 == pytest.approx(lay.bank_bay.y0)
    assert lay.boost_pocket.z0 == pytest.approx(lay.wall)
    assert box_gap(lay.boost_pocket, lay.bank_bay) == pytest.approx(0.0)


# --- lid ------------------------------------------------------------------------------

def test_lid(lay):
    m = MONITORS[L.DESIGN_MONITOR]
    w, s = lay.wall, L.SLACK
    o = lay.lid_outer
    hy, hz = lay.hinge_axis
    # the base footprint, in the lid frame (origin on the hinge axis)
    assert (o.x0, o.x1) == pytest.approx((lay.outer.x0, lay.outer.x1))
    assert (o.y0 + hy, o.y1 + hy) == pytest.approx((lay.outer.y0, lay.outer.y1))
    assert o.z0 == pytest.approx(0.0) and hz == pytest.approx(lay.rim_z)
    assert o.size[2] == pytest.approx(w + L.TAPE_T + m.panel[2] + L.CLOSED_CLEARANCE)

    ms = lay.monitor_space
    inner = Box(o.x0 + w, o.y0 + w, o.z0, o.x1 - w, o.y1 - w, o.z1 - w)
    assert _inside(ms, inner)
    assert ms.size[0] == pytest.approx(m.panel[0] + 2 * s)
    assert ms.size[1] == pytest.approx(m.panel[1] + 2 * s)
    assert ms.y0 == pytest.approx(inner.y0)                       # at the free edge
    assert ms.z0 == pytest.approx(L.CLOSED_CLEARANCE)              # face above the seam
    assert ms.z1 == pytest.approx(inner.z1 - L.TAPE_T)             # back on the tape
    assert ms.size[2] == pytest.approx(m.panel[2])
    assert L.exit_edge(m) == "bottom"                              # cable edge to the hinge

    st = lay.lid_strip
    assert _inside(st, inner)
    assert st.y0 == pytest.approx(ms.y1) and st.y1 == pytest.approx(inner.y1)
    assert (st.x0, st.x1) == pytest.approx((inner.x0, inner.x1))


def test_fits_beds():
    lay = L.layout(L.ROUTES["printed"])
    for b in (lay.outer, lay.lid_outer):
        assert b.size[0] <= L.PRINT_BED[0] and b.size[1] <= L.PRINT_BED[1]


# --- hinge and catch ------------------------------------------------------------------

def test_hinge_axis_inset(lay):
    hy, hz = lay.hinge_axis
    assert hy == pytest.approx(lay.outer.y1 - L.KNUCKLE_R)
    assert hz == pytest.approx(lay.rim_z)
    # the knuckles' circle stays inside base + closed lid
    assert hy + L.KNUCKLE_R <= lay.outer.y1 + EPS
    assert hz + L.KNUCKLE_R <= hz + lay.lid_outer.z1 + EPS


def test_hinge_notch(lay):
    m = MONITORS[L.DESIGN_MONITOR]
    n = lay.hinge_notch
    exit_x = lay.monitor_space.x0 + L.SLACK + m.pigtail_exit_u
    assert (n.x0 + n.x1) / 2 == pytest.approx(exit_x)
    assert n.size[0] == pytest.approx(CABLES["vga-slim"].dia + 2 * L.FIT)
    hy, hz = lay.hinge_axis
    assert n.y0 < hy < n.y1 and n.z0 < hz < n.z1
    closed = Box(0.0, 0.0, 0.0, lay.outer.x1, lay.outer.y1, lay.rim_z + lay.lid_outer.z1)
    assert _inside(n, closed)


def test_lid_catch(lay):
    """Two magnets under the front rim, one by each front corner, in blocks
    clear of every board-row keep-out; the lid's partners face them."""
    assert len(lay.lid_catch) == 2
    left, right = sorted(lay.lid_catch, key=lambda c: c.cx)
    keep = list(lay.board_keepouts.values())
    hy, hz = lay.hinge_axis
    for c in (left, right):
        blk = lay.catch_base_block(c)
        assert blk.size == pytest.approx((L.CATCH_BLOCK, L.CATCH_BLOCK, L.CATCH_BLOCK_H))
        assert blk.y0 == pytest.approx(lay.wall) and blk.z1 == pytest.approx(lay.rim_z)
        assert blk.x0 >= lay.wall - EPS and blk.x1 <= lay.outer.x1 - lay.wall + EPS
        assert not any(_xy_overlap(blk, k) for k in keep), c.what
        assert c.z1 == pytest.approx(lay.rim_z - L.MAGNET_RECESS)
        assert c.z1 - c.z0 == pytest.approx(L.MAGNET_T) and 2 * c.r == pytest.approx(L.MAGNET_D)
        m = lay.catch_lid_magnet(c)
        assert (m.cx, m.cy + hy) == pytest.approx((c.cx, c.cy))
        assert (hz + m.z0) - c.z1 == pytest.approx(2 * L.MAGNET_RECESS)
        # the lid's block is in its front rim, clear of the monitor
        lb = lay.catch_lid_block(c)
        assert lb.y0 == pytest.approx(lay.lid_outer.y0 + lay.wall)
        assert box_gap(lb, lay.monitor_space) >= 0.0
    # nearest each corner: nothing in the way, so each block is against its side wall
    assert lay.catch_base_block(left).x0 == pytest.approx(lay.wall)
    assert lay.catch_base_block(right).x1 == pytest.approx(lay.outer.x1 - lay.wall)


def test_lid_catch_moves_past_a_keepout(monkeypatch):
    """A keep-out over the left corner pushes the block to its +X side."""
    real = L._board_keepouts

    def fake(origin, adapter):
        k = dict(real(origin, adapter))
        k["test/blocker"] = Box(0.0, 0.0, 0.0, 10.0, 20.0, 1.0, "test blocker")
        return k
    monkeypatch.setattr(L, "_board_keepouts", fake)
    lay = L.layout(L.ROUTES["printed"])
    left = min(lay.lid_catch, key=lambda c: c.cx)
    blk = lay.catch_base_block(left)
    assert blk.x0 == pytest.approx(10.0)
    assert not any(_xy_overlap(blk, k) for k in lay.board_keepouts.values())


def test_lid_catch_raises_naming_the_keepout(monkeypatch):
    real = L._board_keepouts

    def fake(origin, adapter):
        k = dict(real(origin, adapter))
        k["test/blocker"] = Box(0.0, 0.0, 0.0, 1000.0, 20.0, 1.0, "test blocker")
        return k
    monkeypatch.setattr(L, "_board_keepouts", fake)
    with pytest.raises(ValueError, match="test blocker"):
        L.layout(L.ROUTES["printed"])


# --- lid motion (kept from the merged layout) -----------------------------------------

def test_lid_profile_rotates_about_hinge(lay):
    hy, hz = lay.hinge_axis
    o = lay.lid_outer
    closed = lay.lid_profile_yz(0.0)
    assert closed.bounds == pytest.approx((hy + o.y0, hz, hy + o.y1, hz + o.z1))
    open_ = lay.lid_profile_yz(L.LID_OPEN_DEG)
    a = math.radians(L.LID_OPEN_DEG)
    front = (hy + o.y0 * math.cos(a), hz - o.y0 * math.sin(a))
    assert front[0] > hy and front[1] > hz + 0.9 * abs(o.y0)
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


def test_tinyvga_offset_places_the_keepout(lay):
    """The TinyVGA offset is one function the layout and the scene share."""
    for key in BOARD_KEYS:
        dx, dy, dz = L.tinyvga_offset(key)
        u = TINYVGA.pcb.union(TINYVGA.de15).union(TINYVGA.plug_keepout(not lay.vga_adapter))
        k = lay.board_keepouts[f"{key}/tinyvga"]
        lo = _to_base(lay, u.x0 + dx, u.y1 + dy, u.z0 + dz)
        assert (k.x0, k.y0, k.z0) == pytest.approx(lo)
