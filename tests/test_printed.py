"""The 3D-printed body (route "printed", ``layout(2.4)``) and its assembly."""

import math

import cadquery as cq
import pytest

from demobox import checks as C
from demobox import layout as L
from demobox.clash import clashes
from demobox.geom import BedOverflow
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS
from demobox.printed import body as B
from demobox.shared import hinge as H
from demobox.shared import inserts as I

@pytest.fixture(scope="module")
def lay():
    return L.layout(L.ROUTES["printed"])


@pytest.fixture(scope="module")
def parts(lay):
    return B.printed_parts(lay)


def _inside(shape, p) -> bool:
    return shape.isInside(cq.Vector(*p), 1e-4)


# --- the parts list ------------------------------------------------------------

def test_parts_list(parts):
    want = {"base", "deck", "lid", "drawer", "hinge-base", "hinge-lid", "mt1-pin", "bezel-clip"}
    want |= {f"bezel-{k}" for k in MONITORS} | {f"retainer-{k}" for k in MONITORS}
    want |= {f"packing-{k}" for k in BATTERIES}
    assert set(parts) == want


def test_every_part_is_one_valid_solid(parts):
    for name, p in parts.items():
        solids = p.solid.Solids()
        assert len(solids) == 1, (name, len(solids))
        assert p.solid.isValid(), name
        assert p.note, name


def test_every_part_fits_the_bed_in_its_print_orientation(parts):
    for name, p in parts.items():
        bb = B.posed(p).BoundingBox()
        assert bb.xmin == pytest.approx(0.0, abs=1e-6) and bb.ymin == pytest.approx(0.0, abs=1e-6)
        assert bb.zmin == pytest.approx(0.0, abs=1e-6), name
        assert bb.xlen <= L.PRINT_BED[0] + 1e-6 and bb.ylen <= L.PRINT_BED[1] + 1e-6, \
            (name, bb.xlen, bb.ylen)


def test_print_orientation_puts_a_face_on_the_bed(parts):
    """The pose puts a flat face of every part at Z = 0, and for the bodies
    it is the face they are designed to print on."""
    for name, p in parts.items():
        assert B.bed_contact_area(B.posed(p)) > 0, name
    o = L.layout(2.4).outer
    assert B.posed(parts["base"]).BoundingBox().zlen == pytest.approx(o.size[2])   # floor down
    assert B.posed(parts["lid"]).BoundingBox().zlen == pytest.approx(
        L.layout(2.4).lid_outer.size[2])                        # back down, nothing proud
    lid = B.posed(parts["lid"])
    # back plate down: the pocket opens upwards, so its centre is empty high up
    bb = lid.BoundingBox()
    assert not _inside(lid, (bb.xlen / 2, bb.ylen / 2, bb.zlen - 1.0))
    assert _inside(lid, (bb.xlen / 2, bb.ylen / 2, 1.0))


def test_oversized_part_raises_bed_overflow_naming_part_and_size(lay):
    """Review Focus 5: a part that does not fit fails the export, naming it."""
    drawer = B.drawer(lay)
    with pytest.raises(BedOverflow, match=r"drawer 197\.80 x 88\.10 mm"):
        B.check_bed("drawer", drawer, (150.0, 220.0))
    with pytest.raises(BedOverflow, match=r"drawer 197\.80 x 88\.10 mm"):
        B.printed_parts(lay, bed=(190.0, 220.0))


def test_unsplittable_body_raises_bed_overflow(lay):
    """Halves that still do not fit are a BedOverflow, not an unprintable STL."""
    with pytest.raises(BedOverflow, match=r"base 214\.50 x 210\.25 mm"):
        B.split_base(lay, bed=(100.0, 220.0))


# --- the split -----------------------------------------------------------------

@pytest.fixture(scope="module")
def split(lay):
    return B.split_base(lay, bed=(200.0, 220.0))


def test_over_bed_base_splits_left_and_right(split):
    pieces, info = split
    assert set(pieces) == {"base-left", "base-right", "deck-left", "deck-right"}
    for name, p in pieces.items():
        bb = B.posed(p).BoundingBox()
        assert bb.xlen <= 200.0 + 1e-6 and bb.ylen <= 220.0 + 1e-6, name
        assert len(p.solid.Solids()) == 1, name
    assert info.axis == "x"
    assert pieces["base-left"].solid.BoundingBox().xmax == pytest.approx(info.at, abs=1e-6)
    assert pieces["base-right"].solid.BoundingBox().xmin == pytest.approx(info.at, abs=1e-6)


def test_split_is_at_the_shortest_section(lay, split):
    _, info = split
    tub = B.base_tub(lay)
    best = B.section_area(tub, "x", info.at)
    for s in info.candidates:
        assert best <= B.section_area(tub, "x", s) + 1e-6, s


def test_split_joints_have_heatset_screws_and_pins(split):
    pieces, info = split
    left, right = pieces["base-left"].solid, pieces["base-right"].solid
    fronts = [j for j in info.joints if j.wall == "front"]
    backs = [j for j in info.joints if j.wall == "back"]
    assert fronts and backs
    for j in info.joints:
        sx, sy, sz = j.screw
        # clearance hole through the left block, heat-set hole in the right
        assert not _inside(left, (sx - 1.0, sy, sz))
        assert _inside(left, (sx - 1.0, sy + B.SCREW_CLEAR_D / 2 + 0.2, sz))
        assert not _inside(right, (sx + L.HEATSET_DEPTH / 2, sy + L.HEATSET_HOLE_D / 2 - 0.05, sz))
        assert _inside(right, (sx + L.HEATSET_DEPTH / 2, sy + L.HEATSET_HOLE_D / 2 + 0.05, sz))
        assert _inside(right, (sx + L.HEATSET_DEPTH + 0.3, sy, sz))
        px, py, pz = j.pin
        for piece, x in ((left, px - 1.0), (right, px + 1.0)):
            assert not _inside(piece, (x, py, pz))
            assert _inside(piece, (x, py + B.DOWEL_HOLE_D / 2 + 0.2, pz))
    assert any(h.what.startswith("joint") for h in pieces["base-right"].heatsets)


# --- heat-set inserts ----------------------------------------------------------

def test_heatset_holes_are_4_mm(parts):
    """Every heat-set hole is HEATSET_HOLE_D (4.0) across and HEATSET_DEPTH deep
    with material round and below it."""
    assert L.HEATSET_HOLE_D == 4.0
    count = 0
    for name, p in parts.items():
        for h in p.heatsets:
            count += 1
            d = cq.Vector(*h.axis)
            mouth = cq.Vector(*h.at)
            side = d.cross(cq.Vector(0, 0, 1)) if abs(d.z) < 0.9 else cq.Vector(1, 0, 0)
            side = side.normalized()
            mid = mouth + d * (L.HEATSET_DEPTH / 2)
            r = L.HEATSET_HOLE_D / 2
            assert not _inside(p.solid, (mid).toTuple()), (name, h.what)
            assert not _inside(p.solid, (mid + side * (r - 0.05)).toTuple()), (name, h.what)
            assert _inside(p.solid, (mid + side * (r + 0.05)).toTuple()), (name, h.what)
            assert _inside(p.solid, (mouth + d * (L.HEATSET_DEPTH + 0.3)).toTuple()), \
                (name, h.what)
    assert count >= 1 + 4 + 2 + 3 + 1 + 4  # MT2, base leaf, lid leaf, bezel, clip, deck corners


def test_hinge_leaf_screws_have_heatset_bosses(parts, lay):
    """Carry-forward 3: an insert behind every leaf screw hole."""
    base = {(round(h.at[0], 3), round(h.at[2], 3)) for h in parts["base"].heatsets
            if h.what.startswith("hinge leaf")}
    assert base == {(round(x, 3), round(z, 3)) for x, z in H.base_leaf_screws(lay)}
    lid = {(round(h.at[0], 3), round(h.at[2], 3)) for h in parts["lid"].heatsets
           if h.what.startswith("hinge leaf")}
    assert lid == {(round(x, 3), round(z, 3)) for x, z in H.lid_leaf_screws(lay)}


def test_bezel_screws_line_up_with_lid_inserts(parts, lay):
    """R15: an insert in the lid under each of the bezel's holes."""
    lid = {(round(h.at[0], 3), round(h.at[1], 3)) for h in parts["lid"].heatsets
           if h.what.startswith("bezel")}
    assert lid == {(round(x, 3), round(y, 3)) for x, y in I.bezel_screws(lay)}
    for h in parts["lid"].heatsets:
        if h.what.startswith("bezel"):
            assert h.at[2] == pytest.approx(L.INSERT_MATERIAL)   # on the bezel's back
            assert h.axis == (0.0, 0.0, 1.0)


# --- features ----------------------------------------------------------------------

def test_knuckle_relief_round_the_axis(parts, lay):
    """Carry-forward 1: base and lid are cut back to KNUCKLE_R + FIT round the
    hinge axis along each knuckle group, and kept elsewhere."""
    hy, hz = lay.hinge_axis
    r = H.KNUCKLE_R + L.FIT
    u = lay.wall / 2                                   # mid-wall
    v_in = math.sqrt((r - 0.1) ** 2 - u ** 2)          # just inside the relief
    v_out = math.sqrt((r + 0.3) ** 2 - u ** 2)         # just outside it
    for x0, x1 in H.hinge_groups(lay):
        for x in (x0 + 0.5, (x0 + x1) / 2, x1 - 0.5):
            assert not _inside(parts["base"].solid, (x, hy - u, hz - v_in))
            assert _inside(parts["base"].solid, (x, hy - u, hz - v_out))
            assert not _inside(parts["lid"].solid, (x, -u, v_in))
            assert _inside(parts["lid"].solid, (x, -u, v_out))
    # beside the groups the corner is kept
    x = H.hinge_groups(lay)[0][1] + 5.0
    assert _inside(parts["base"].solid, (x, hy - u, hz - v_in))


def test_hinge_cable_channel_split_between_base_and_lid(parts, lay):
    """Carry-forward 5: the channel's base part is cut from the base (deck to
    the axis), its lid part from the lid, in the lid frame."""
    base_part, lid_part = B.channel_parts(lay)
    c = lay.hinge_cable_channel
    hy, hz = lay.hinge_axis
    assert base_part.z1 == pytest.approx(hz) and lid_part.z0 == pytest.approx(0.0)
    assert lid_part.y1 == pytest.approx(0.0) and lid_part.z1 == pytest.approx(c.z1 - hz)
    cx = (c.x0 + c.x1) / 2
    # the back wall is open across the channel, closed beside it
    assert not _inside(parts["base"].solid, (cx, hy - lay.wall / 2, (lay.deck_z + hz) / 2))
    assert _inside(parts["base"].solid, (c.x1 + 5.0, hy - lay.wall / 2, (lay.deck_z + hz) / 2))
    # ... and so is the lid's hinge-end wall
    assert not _inside(parts["lid"].solid, (cx, -lay.wall / 2, lid_part.z1 / 2))
    assert _inside(parts["lid"].solid, (c.x1 + 5.0, -lay.wall / 2, lid_part.z1 / 2))


def test_mt1_boss_has_a_peg_hole_per_revision(parts, lay):
    deck = parts["deck"].solid
    for peg in lay.pegs.values():
        assert not _inside(deck, (peg.cx, peg.cy, lay.deck_z + 1.0))
        assert _inside(deck, (peg.cx + peg.r + 0.3, peg.cy, lay.deck_z + 1.0))


def test_drawer_detent_and_end_stop(lay):
    """Closed, the bump sits in the notch clear of everything; pulled out by
    drawer_travel, its square face meets the groove's end (the stop)."""
    tub, drawer = B.base_tub(lay), B.drawer(lay)
    assert tub.intersect(drawer).Volume() <= 1e-3
    out = drawer.translate(cq.Vector(-lay.drawer_travel, 0, 0))
    assert tub.intersect(out).Volume() <= 1e-3
    beyond = drawer.translate(cq.Vector(-lay.drawer_travel - 0.5, 0, 0))
    assert tub.intersect(beyond).Volume() > 0.05   # the stop blocks further travel
    # the ridge must be ridden over to leave the closed position: a click
    nudge = drawer.translate(cq.Vector(-1.0, 0, 0))
    assert tub.intersect(nudge).Volume() > 0.01


def test_boost_pocket_is_clear(parts, lay):
    b = lay.boost_pocket
    box = cq.Solid.makeBox(*b.size, cq.Vector(b.x0, b.y0, b.z0))
    assert parts["base"].solid.intersect(box).Volume() <= 1e-6


# --- assembly ----------------------------------------------------------------------

def _clashes(items):
    return clashes(items, B.DECLARED_OVERLAPS)


@pytest.mark.parametrize("angle", [0.0, L.LID_OPEN_DEG])
def test_assembly_has_no_intersections(angle):
    items = B.assembly("printed", angle, 0.0)
    names = [n for n, _, _ in items]
    assert len(names) == len(set(names))
    for n in ("base", "deck", "lid", "drawer", "hinge-base", "hinge-lid"):
        assert n in names
    assert _clashes(items) == []


def test_assembly_drawer_out_has_no_intersections(lay):
    items = B.assembly("printed", 0.0, lay.drawer_travel)
    assert _clashes(items) == []


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(MONITORS))
def test_assembly_each_monitor(key):
    items = B.assembly("printed", 0.0, 0.0, monitor=key)
    assert _clashes(items) == []


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(BATTERIES))
def test_assembly_each_bank(key):
    items = B.assembly("printed", 0.0, 0.0, bank=key)
    assert _clashes(items) == []


def test_assembly_lid_turns_about_the_axis(lay):
    closed = dict((n, s) for n, s, _ in B.assembly("printed", 0.0, 0.0))
    opened = dict((n, s) for n, s, _ in B.assembly("printed", L.LID_OPEN_DEG, 0.0))
    assert closed["lid"].BoundingBox().zmin == pytest.approx(lay.outer.z1)
    assert opened["lid"].BoundingBox().zmax > lay.outer.z1 + 150.0
    assert closed["base"].BoundingBox().xlen == opened["base"].BoundingBox().xlen


def test_assembly_unknown_route():
    with pytest.raises(ValueError, match="unknown route"):
        B.assembly("cnc", 0.0, 0.0)


def test_over_bed_lid_splits_with_joints(lay):
    """The lid splits like the base on a bed narrower than it (but wide
    enough for the bezel), joined at its front band and hinge-end gutter."""
    pieces, info = B.split_lid(lay, bed=(210.0, 220.0))
    assert set(pieces) == {"lid-left", "lid-right"}
    assert {j.wall for j in info.joints} == {"front", "hinge"}
    for name, p in pieces.items():
        bb = B.posed(p).BoundingBox()
        assert bb.xlen <= 210.0 + 1e-6 and bb.ylen <= 220.0 + 1e-6, name
    best = B.section_area(B.lid(lay), "x", info.at)
    assert all(best <= B.section_area(B.lid(lay), "x", s) + 1e-6 for s in info.candidates)


# --- R17: bezel clip; R18: no solid lumps; bridges; detent pad; hardware -------------

def test_bezel_front_left_corner_is_clipped(lay, parts):
    """R17: the opening corner without a bezel screw (the pocket's front-left)
    is held by a flat printed clip screwed into a lid insert, clamping the
    bezel's corner face to face; the clip prints flat and covers no window."""
    x0, y0, x1, _ = I.lid_opening(lay)
    screws = B.clip_screws(lay)
    assert len(screws) == 1 and screws[0][0] < (x0 + x1) / 2      # front-left only
    (sx, sy), = screws
    clip = B.bezel_clip(lay, sx, sy)
    bb = clip.BoundingBox()
    assert bb.zmax == pytest.approx(0.0) and bb.zlen == pytest.approx(B.CLIP_T)
    # it lies over the bezel's corner (in front of it, screen side) ...
    assert _inside(clip, (x0 + L.FIT + 1.0, y0 + L.FIT + 1.0, -B.CLIP_T / 2))
    assert bb.ymax == pytest.approx(y0 + L.FIT + B.CLIP_OVER)
    for m in MONITORS.values():
        bezel = I.monitor_bezel(m, lay).val()
        assert clip.intersect(bezel).Volume() <= 1e-6
        assert bezel.BoundingBox().zmin == pytest.approx(bb.zmax)   # clamps it
        wx0, wy0, wx1, wy1 = I._panel_rect(m, lay, C.monitor_window(m))
        assert bb.xmax <= wx0 or bb.xmin >= wx1 or bb.ymax <= wy0 or bb.ymin >= wy1
    # ... its screw goes into the lid's insert, through the clip's hole
    hs = [h for h in parts["lid"].heatsets if h.what == "clip screw (bezel corner)"]
    assert [(round(h.at[0], 6), round(h.at[1], 6)) for h in hs] == [(round(sx, 6), round(sy, 6))]
    assert not _inside(clip, (sx, sy, -B.CLIP_T / 2))
    # printed flat: the whole plate is on the bed
    p = parts["bezel-clip"]
    assert B.bed_contact_area(B.posed(p)) == pytest.approx(clip.Volume() / B.CLIP_T)


def test_lid_has_nothing_below_its_face(lay):
    """Printed screen side up, nothing of the lid overhangs its face."""
    assert B.lid(lay).BoundingBox().zmin == pytest.approx(0.0)


def test_lid_front_band_is_hollow_and_ribbed(lay):
    """R18, direct: the band's cells are empty but for the clip's boss and the
    lid catch's blocks (R22), the
    ribs between them are ``wall`` thick, and no cell (the screen-side skin's
    bridge when printed) is wider than RIB_SPAN_MAX."""
    lid, cells = B.lid(lay), B.front_cavities(lay)
    assert len(cells) >= 2
    assert max(c.size[1] for c in cells) <= B.RIB_SPAN_MAX
    for a, b in zip(cells, cells[1:]):
        assert b.y0 - a.y1 == pytest.approx(lay.wall)
    bosses = [B.clip_boss(lay, x, y) for x, y in B.clip_screws(lay)]
    bosses += [lay.catch_lid_block(c) for c in lay.lid_catch]
    allowed = 0.0
    for c in cells:
        for b in bosses:
            dx = min(b.x1, c.x1) - max(b.x0, c.x0)
            dy = min(b.y1, c.y1) - max(b.y0, c.y0)
            dz = min(b.z1, c.z1) - max(b.z0, c.z0)
            allowed += max(dx, 0) * max(dy, 0) * max(dz, 0)
    held = sum(lid.intersect(cq.Solid.makeBox(*c.size, cq.Vector(c.x0, c.y0, c.z0))).Volume()
               for c in cells)
    assert held <= allowed + 1e-3
    assert sum(c.size[0] * c.size[1] * c.size[2] for c in cells) > 150_000   # really hollow


def test_drawer_opening_has_no_long_bridge(lay):
    """The opening's top is 45 degree peaks: no downward-facing flat face in
    the left wall over the drawer is wider than OPENING_PITCH (a flat 88 mm
    top would sag onto the drawer)."""
    tub, w = B.base_tub(lay), lay.wall
    for f in tub.Faces():
        if f.geomType() != "PLANE" or f.normalAt().z > -0.99:
            continue
        bb = f.BoundingBox()
        if bb.xmax <= w + 1e-6 and bb.zmin > w + 1e-6 and bb.zmax < lay.deck_z:
            assert bb.ylen <= B.OPENING_PITCH, (bb.ylen, bb.zmin)
    # the drawer face fills it, FIT clear, shut and out at the stop
    drawer = B.drawer(lay)
    assert tub.intersect(drawer).Volume() <= 1e-3
    assert tub.intersect(drawer.translate(cq.Vector(-lay.drawer_travel, 0, 0))).Volume() <= 1e-3
    face_top = max(v.Z for v in drawer.Vertices() if v.X < w + 1e-6)
    assert face_top > lay.bay.z1 + 1.0                  # the face's peaks


def test_screw_heads_clear_when_shut_and_open():
    """Bought hardware proud of the screen face (the bezel and clip screws'
    pan heads) is in the assembly as keep-outs and clears everything."""
    for angle in (0.0, L.LID_OPEN_DEG):
        items = B.assembly("printed", angle, 0.0)
        heads = [n for n, _, _ in items if n.startswith("hw:") and "magnet" not in n]
        assert len(heads) == len(I.bezel_screws(L.layout(2.4))) + 1
        assert _clashes(items) == []


def test_bodies_have_no_solid_lumps(lay):
    """R18, every body: mean thickness 2V/A at most MAX_MEAN_THICKNESS x wall
    (justified in body's docstring)."""
    for name, f in (("base", B.base_tub), ("deck", B.deck), ("drawer", B.drawer),
                    ("lid", B.lid)):
        t = B.mean_thickness(f(lay)) / lay.wall
        assert t <= B.MAX_MEAN_THICKNESS, (name, t)


def test_detent_groove_leaves_a_full_wall(lay):
    """The front wall behind the detent groove is at least ``wall`` thick."""
    tub = B.base_tub(lay)
    det = B._detent(lay)
    x, z = (det["g0"] + det["g1"]) / 2, (det["bz0"] + det["bz1"]) / 2
    groove_bottom = lay.wall - B.GROOVE_D
    assert not _inside(tub, (x, groove_bottom + 0.05, z))
    assert _inside(tub, (x, groove_bottom - lay.wall + 0.05, z))


def test_nothing_stands_below_the_printed_floor():
    """R19, printed route: no screw goes through the tub's floor (its screws go
    into heat-set inserts from inside or from the sides), so nothing stands
    below Z = 0 and the box needs no feet."""
    items = B.assembly("printed", 0.0, 0.0)
    assert min(s.BoundingBox().zmin for _, s, _ in items) == pytest.approx(0.0, abs=1e-6)
    assert not [n for n, _, _ in items if n.startswith("hw:") and "foot" in n]


# --- screws into heat-set inserts (review fix round 1) ---------------------------

def test_insert_screw_is_the_longest_that_stops_short():
    from demobox.shared import m3
    # 1.2 mm bezel into a 5.7 mm hole: 6.4 allowed -> M3 x 6, 4.8 engaged
    assert m3.insert_screw(1.2, L.HEATSET_DEPTH) == 6
    # rounding up (stock_length) would give M3 x 8 for the 1.6 mm board: 6.4 > 5.2
    assert m3.insert_screw(1.6, L.HEATSET_DEPTH) == 6
    with pytest.raises(ValueError):
        m3.insert_screw(1.2, 3.0)          # nothing engages 3 mm of a 3 mm hole


def test_every_insert_screw_engages_and_stops_short(lay, parts, split):
    """Every screw into a heat-set insert -- bezel, clip, hinge leaves, board,
    deck corners and split joints (base and lid) -- engages at least 3 mm and
    stops at least 0.5 mm short of the 5.7 mm hole's floor."""
    from demobox.shared import m3
    lid_pieces, _ = B.split_lid(lay, bed=(210.0, 220.0))
    base_pieces, _ = split
    heatsets = [h for group in (parts, base_pieces, lid_pieces)
                for p in group.values() for h in p.heatsets]
    screws = B.insert_screws(lay, heatsets)
    labels = {s.what for s in screws}
    assert {"bezel", "bezel clip", "hinge leaves", "board, MT2", "deck corners",
            "split joints"} <= labels
    for s in screws:
        assert m3.MIN_ENGAGE <= s.engagement <= L.HEATSET_DEPTH - m3.INSERT_SHORT, s


def test_hardware_lists_the_insert_screws(lay):
    hw = B.hardware(lay)
    assert hw["M3 x 6 pan-head (board, MT2)"] == 1
    assert hw["M3 x 6 pan-head (deck corners)"] == 4
    assert sum(n for k, n in hw.items() if k.startswith("M3 heat-set insert")) == 15


@pytest.mark.slow
@pytest.mark.parametrize("angle", range(10, 100, 10))
def test_assembly_intermediate_lid_angles_have_no_intersections(angle):
    """The lid's whole swing, not just shut and fully open (finding 7)."""
    assert _clashes(B.assembly("printed", float(angle), 0.0)) == []


@pytest.mark.slow
@pytest.mark.parametrize("route", ["printed", "laser"])
def test_lid_catch_magnets_face_each_other_when_shut(route):
    """R22, in real solids: with the lid shut every catch magnet in the lid
    sits straight over one in the base, <= 1 mm apart; the whole assembly,
    magnets included, is clash-free (the 0 degree assembly test, both routes)."""
    items = dict((n, s) for n, s, _ in B.assembly(route, 0.0, 0.0))
    base = sorted(n for n in items if n.startswith("hw:catch-magnet-base-"))
    lid = sorted(n for n in items if n.startswith("hw:catch-magnet-lid-"))
    assert len(base) == len(lid) == 2
    for nb, nl in zip(base, lid):
        a, b = items[nb].BoundingBox(), items[nl].BoundingBox()
        assert (a.center.x, a.center.y) == pytest.approx((b.center.x, b.center.y))
        gap = b.zmin - a.zmax
        assert 0 <= gap <= 1.0
    if route == "printed":
        assert _clashes(list(B.assembly("printed", 0.0, 0.0))) == []
