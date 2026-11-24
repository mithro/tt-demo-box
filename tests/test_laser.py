"""The laser-cut body (route "laser", ``layout(3.0)``): joints, panels, the
bed, the drawer and its latch, the assembly and the DXF export."""

import subprocess
import sys
from pathlib import Path

import cadquery as cq
import pytest

from demobox import layout as L
from demobox.clash import clashes
from demobox.geom import BedOverflow, overlaps
from demobox.laser import joints as J
from demobox.laser import panels as P
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS
from demobox.printed import body as B
from demobox.shared import hinge as H
from demobox.shared import inserts as I

ROOT = Path(__file__).resolve().parent.parent
WALL = L.ROUTES["laser"]


@pytest.fixture(scope="module")
def lay():
    return L.layout(WALL)


@pytest.fixture(scope="module")
def body(lay):
    return P.build(lay, WALL, P.KERF)


@pytest.fixture(scope="module")
def thin():
    """Review Focus 4: plywood sold as 3 mm measuring 2.7, a wider kerf."""
    return P.build(L.layout(2.7), 2.7, 0.2)


def _inside(shape, p) -> bool:
    return shape.isInside(cq.Vector(*p), 1e-4)


def _fingers(edge, t):
    """(start, end) of the runs of an edge profile standing proud (y < t/2)."""
    out, start = [], None
    for (x0, y0), (x1, y1) in zip(edge, edge[1:]):
        if y0 < t / 2 and y1 < t / 2 and x1 != x0:
            start = x0 if start is None else start
            end = x1
        elif start is not None and x0 == x1:
            out.append((start, end))
            start = None
    if start is not None:
        out.append((start, end))
    return out


# --- joints -------------------------------------------------------------------------

@pytest.mark.parametrize("length, t, n", [(100.0, 3.0, 11), (10.0, 3.0, 3), (45.0, 3.0, 5),
                                          (54.0, 3.0, 7), (5.0, 3.0, 3), (90.0, 2.7, 11)])
def test_finger_count_is_the_nearest_odd_at_least_3(length, t, n):
    assert J.finger_count(length, t) == n


@pytest.mark.parametrize("t, kerf", [(3.0, 0.15), (2.7, 0.2), (3.2, 0.0)])
@pytest.mark.parametrize("length", [27.0, 100.0, 203.55])
def test_male_and_female_edges_are_complementary(length, t, kerf):
    """Male fingers grow kerf/2 each side, the female's slots shrink by kerf/2;
    with that taken off, the two sets of fingers tile the edge, each finger
    starting where the mate's ends."""
    male = _fingers(J.finger_edge(length, t, kerf, True), t)
    female = _fingers(J.finger_edge(length, t, kerf, False), t)
    n = J.finger_count(length, t)
    assert len(male) == (n + 1) // 2 and len(female) == (n - 1) // 2
    k = kerf / 2
    # the male's end fingers run to the edge's ends (and kerf/2 past them)
    assert male[0][0] == pytest.approx(-k) and male[-1][1] == pytest.approx(length + k)
    nominal = sorted([(a + k, b - k) for a, b in male] + [(a + k, b - k) for a, b in female])
    nominal[0] = (0.0, nominal[0][1])
    nominal[-1] = (nominal[-1][0], length)
    assert sum(b - a for a, b in nominal) == pytest.approx(length)
    for (_, b0), (a1, _) in zip(nominal, nominal[1:]):
        assert a1 == pytest.approx(b0)                         # offsets equal
    # the profile's depths: tips kerf/2 proud of the edge, slot floors at t - kerf/2
    ys = {round(y, 9) for _, y in J.finger_edge(length, t, kerf, True)}
    assert ys == {round(-k, 9), round(t - k, 9)}


def test_tslot_takes_an_m3x12_and_a_square_nut():
    t = 3.0
    poly = J.tslot(50.0, t)
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    assert min(ys) == 0.0                                       # open at the edge
    assert max(ys) >= J.TSLOT_SCREW - t                         # the screw's tip fits
    from shapely.geometry import Polygon, box
    sl = Polygon(poly)
    assert sl.is_valid
    # the shank slot is the clearance width, centred on ``at``
    assert sl.intersection(box(0, 0.1, 100, 0.2)).bounds[0] == pytest.approx(50 - J.SLOT_W / 2)
    # the nut pocket takes a square nut across and its thickness along the screw
    y0, y1 = J.nut_pocket(t)
    assert y1 - y0 >= J.NUT_T and max(xs) - min(xs) >= J.NUT_W
    assert y1 <= J.TSLOT_SCREW - t - J.THREAD_PAST + 1e-9       # the screw passes the nut


# --- panels -----------------------------------------------------------------------

def test_panel_set(body):
    names = set(body.panels)
    for want in ("base-front", "base-back", "base-left", "base-right", "lid-front",
                 "lid-left", "lid-right", "lid-hinge-left", "lid-hinge-right", "lid-band-face",
                 "lid-band-wall", "drawer-face", "drawer-back", "drawer-side-front",
                 "drawer-side-back", "drawer-floor", "drawer-guide", "runner-front",
                 "runner-back"):
        assert want in names, want
    # R9: the base floor, deck and lid back are too big for the bed and are split
    for big in ("base-floor", "deck", "lid-back"):
        assert big not in names
        assert sum(1 for n in names if n.startswith(big + "-")) == 2, big


def test_every_panel_is_one_valid_piece(body):
    for name, p in body.panels.items():
        assert p.shape.geom_type == "Polygon" and p.shape.is_valid, name
        s = p.solid()
        assert len(s.Solids()) == 1 and s.isValid(), name
        bb = s.BoundingBox()
        assert min(bb.xlen, bb.ylen, bb.zlen) == pytest.approx(p.t), name


@pytest.mark.parametrize("which", ["body", "thin"])
def test_every_panel_fits_the_laser_bed(which, body, thin):
    b = body if which == "body" else thin
    for name, p in b.panels.items():
        w, h = sorted(p.cut_size(), reverse=True)
        assert w <= L.LASER_BED[0] + 1e-6 and h <= L.LASER_BED[1] + 1e-6, (name, w, h)


def test_bed_overflow_names_the_panel_and_its_size(lay):
    with pytest.raises(BedOverflow, match=r"[a-z-]+ \d+\.\d\d x \d+\.\d\d mm does not fit the "
                                          r"150 x 100 mm laser bed"):
        P.build(lay, WALL, P.KERF, bed=(150.0, 100.0))


def test_t_must_match_the_layout(lay):
    with pytest.raises(ValueError, match="layout"):
        P.panels(lay, t=2.7)


@pytest.mark.slow
@pytest.mark.parametrize("which", ["body", "thin"])
def test_every_joint_is_complementary(which, body, thin):
    """Every jointed pair: the segments tile the zone, ownership alternates
    within a finger run, the male owns both ends, and in 3D the zone is filled
    exactly once (the fingers interlock without overlap or gap)."""
    b = body if which == "body" else thin
    assert len(b.joints) >= 30
    solids = {n: p.solid(holes=False) for n, p in b.slab_panels.items()}
    boxes = {n: p.box() for n, p in b.slab_panels.items()}

    def box(bx):
        return cq.Solid.makeBox(*bx.size, cq.Vector(bx.x0, bx.y0, bx.z0))

    for j in b.joints:
        lo, hi = j.interval
        assert j.segments[0][0] == pytest.approx(lo) and j.segments[-1][1] == pytest.approx(hi)
        for (_, a1, _), (b0, _, _) in zip(j.segments, j.segments[1:]):
            assert b0 == pytest.approx(a1)
        for run in j.runs:
            owners = [o for _, _, o in run]
            assert len(run) == J.finger_count(run[-1][1] - run[0][0], b.t)
            assert owners[0] == owners[-1] == j.male
            assert all(x != y for x, y in zip(owners, owners[1:]))
        assert solids[j.a].intersect(solids[j.b]).Volume() <= 1e-3, (j.a, j.b)
        # each segment is its owner's (less the owner's own feature cuts) and nobody else's
        for s0, s1, owner in j.segments:
            seg = box(j.segment_box(s0, s1))
            want = seg
            sb = j.segment_box(s0, s1)
            for c in b.slab_cuts[owner]:
                if overlaps(sb, c):
                    want = want.cut(box(c))
            got = solids[owner].intersect(seg).Volume()
            assert got == pytest.approx(want.Volume(), abs=1e-2), (j.a, j.b, s0, owner)
            for n, s in solids.items():
                if n != owner and overlaps(boxes[n], sb):
                    assert s.intersect(seg).Volume() <= 1e-3, (j.a, j.b, s0, n)


@pytest.mark.parametrize("which", ["body", "thin"])
def test_split_panels_mate_along_a_finger_seam(which, body, thin):
    """R9: each split panel's two pieces are its whole, without overlap, and
    meet along a fingered seam."""
    b = body if which == "body" else thin
    assert {s.name for s in b.seams} == {"base-floor", "deck", "lid-back"}
    for s in b.seams:
        p0, p1 = (b.panels[n] for n in s.pieces)
        assert p0.shape.intersection(p1.shape).area == pytest.approx(0.0, abs=1e-6)
        assert p0.shape.union(p1.shape).area == pytest.approx(s.whole.area, rel=1e-9)
        assert len(s.runs) >= 1 and all(len(r) >= 3 for r in s.runs)


def test_kerf_is_added_to_every_cut_edge(thin):
    """The cut path is the nominal outline grown kerf/2; the beam takes kerf/2
    off it again, leaving the nominal part.  Holes shrink by kerf."""
    k = 0.2
    for name, p in thin.panels.items():
        cut = p.cut_shape()
        back = cut.buffer(-k / 2, join_style=2)
        assert back.symmetric_difference(p.shape).area < 1e-3 * p.shape.length, name
        for (u, v, d), (cu, cv, cd) in zip(p.holes, p.cut_holes()):
            assert (cu, cv) == (u, v) and cd == pytest.approx(d - k)


# --- functions of the box ------------------------------------------------------------

def test_tslot_screws_line_up(body):
    """Every T-slot screw: a clearance hole in the panel it passes through, the
    T-slot (shank slot + nut pocket) in the panel it goes into."""
    assert len(body.screws) >= 16
    for s in body.screws:
        a, b = body.panel_at(s.through, s.at), body.panel_at(s.into, s.at)
        sa, sb = a.solid(), b.solid()
        d = cq.Vector(*s.direction)
        at = cq.Vector(*s.at)
        assert not _inside(sa, (at - d * (a.t / 2)).toTuple()), s
        mid_nut = at + d * (sum(J.nut_pocket(a.t)) / 2)
        assert not _inside(sb, mid_nut.toTuple()), s
        assert not _inside(sb, (at + d * 1.0).toTuple()), s
        assert _inside(sb, (at + d * (J.TSLOT_SCREW - a.t + 2.0)).toTuple()), s


def test_back_wall_has_channel_relief_and_leaf_screws(body, lay):
    back = body.panels["base-back"].solid()
    hy, hz = lay.hinge_axis
    y = hy - WALL / 2
    ch = lay.hinge_cable_channel
    assert not _inside(back, ((ch.x0 + ch.x1) / 2, y, (lay.deck_z + hz) / 2))
    assert _inside(back, ((ch.x0 + ch.x1) / 2, y, lay.deck_z - 1.0))         # one piece
    for x0, x1 in H.hinge_groups(lay):
        assert not _inside(back, ((x0 + x1) / 2, y, hz - H.KNUCKLE_R - L.FIT + 0.2))
    for x, z in H.base_leaf_screws(lay):
        assert not _inside(back, (x, y, z))
        assert _inside(back, (x + 2.5, y, z))
    blocks = [k for k in body.placed if k[0] == "nut-block-base-leaf"]
    assert len(blocks) == len(H.base_leaf_screws(lay))


def test_lid_hinge_wall_and_bezel_retention(body, lay):
    for x, z in H.lid_leaf_screws(lay):
        wall = body.panel_at("lid-hinge", (x, -WALL / 2, z))
        assert not _inside(wall.solid(), (x, -WALL / 2, z))
    assert len([k for k in body.placed if k[0] == "nut-block-lid-leaf"]) == 2
    bezel = [k for k in body.placed if k[0] == "nut-block-bezel"]
    assert len(bezel) == len(I.bezel_screws(lay)) == 3
    # the clip's screw goes into a nut block in the band, in front of the band wall
    (cx, cy), = P.clip_screws(lay, WALL)
    wall = body.panels["lid-band-wall"]
    assert cy < wall.z0 - J.SLOT_W / 2
    assert [k for k in body.placed if k[0] == "nut-block-clip"]
    for x0, x1 in H.hinge_groups(lay):                      # knuckle relief
        xm = (x0 + x1) / 2
        hw = body.panel_at("lid-hinge", (xm, -WALL / 2, 10.0))
        assert not _inside(hw.solid(), (xm, -WALL / 2, H.KNUCKLE_R + L.FIT - 0.2))


def test_magnet_latch(body, lay):
    """Two 6 x 3 mm disc magnets in printed corner blocks, drawer front and
    base front: coaxial and FIT apart when shut."""
    items = dict((n, s) for n, s, _ in P.assembly(0.0, 0.0))
    m = [items[n] for n in items if n.startswith("hw:magnet")]
    assert len(m) == 2
    a, b = (s.BoundingBox() for s in m)
    assert a.xlen == pytest.approx(P.MAGNET_D) and a.zlen == pytest.approx(P.MAGNET_T)
    assert a.center.x == pytest.approx(b.center.x) and a.center.y == pytest.approx(b.center.y)
    assert abs(a.center.z - b.center.z) == pytest.approx(P.MAGNET_T + L.FIT)
    assert {k[1] for k in body.placed} >= {"magnet-block-drawer", "magnet-block-base"}


# --- assembly ------------------------------------------------------------------------

@pytest.mark.parametrize("angle, out", [(0.0, 0.0), (L.LID_OPEN_DEG, 0.0), (0.0, "travel"),
                                        (0.0, "half")])
@pytest.mark.slow
def test_laser_assembly_has_no_intersections(angle, out, lay):
    d = {"travel": lay.drawer_travel, "half": lay.drawer_travel / 2}.get(out, out)
    items = B.assembly("laser", angle, d)
    names = [n for n, _, _ in items]
    assert len(names) == len(set(names))
    assert sum(1 for n in names if n.startswith("hw:nut")) >= 16
    assert clashes(items, P.DECLARED_OVERLAPS) == []


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(MONITORS))
def test_laser_assembly_each_monitor(key):
    assert clashes(B.assembly("laser", 0.0, 0.0, monitor=key), P.DECLARED_OVERLAPS) == []


@pytest.mark.slow
@pytest.mark.parametrize("key", sorted(BATTERIES))
def test_laser_assembly_each_bank(key):
    assert clashes(B.assembly("laser", 0.0, 0.0, bank=key), P.DECLARED_OVERLAPS) == []


def test_laser_lid_turns_about_the_axis(lay):
    closed = dict((n, s) for n, s, _ in B.assembly("laser", 0.0, 0.0))
    opened = dict((n, s) for n, s, _ in B.assembly("laser", L.LID_OPEN_DEG, 0.0))
    back = [n for n in closed if n.startswith("lid-back-")]
    assert min(closed[n].BoundingBox().zmax for n in back) == pytest.approx(
        lay.outer.z1 + lay.lid_outer.z1)
    assert max(opened[n].BoundingBox().zmax for n in back) > lay.outer.z1 + 150.0


def test_laser_printed_parts_fit_the_print_bed(lay):
    parts = P.printed_parts(lay, WALL)
    for want in ("hinge-base", "hinge-lid", "mt1-pin", "bezel-clip", "magnet-block",
                 "catch-block-base", "catch-block-lid",
                 "nut-block-base-leaf", "nut-block-lid-leaf", "nut-block-bezel",
                 "nut-block-clip", "standoff-mt2", "nut-cup-mt2", "deck-support", "mt1-boss"):
        assert want in parts, want
    for name, p in parts.items():
        bb = B.posed(p).BoundingBox()
        assert bb.xlen <= L.PRINT_BED[0] and bb.ylen <= L.PRINT_BED[1], name
        assert len(p.solid.Solids()) == 1, name


def test_hardware_list(lay):
    hw = P.hardware(lay, WALL)
    assert hw["M3 square nut"] >= 16
    assert hw["6 x 3 mm disc magnet"] == 2 + 2 * len(lay.lid_catch)   # drawer latch + lid catch
    assert any(k.startswith("M3 x 12") for k in hw)


# --- export ------------------------------------------------------------------------

def _export(out: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "export_laser.py"),
                           "--out", str(out), "--no-printed", *args],
                          capture_output=True, text=True, cwd=ROOT)


@pytest.mark.slow
def test_export_writes_reproducible_dxf_per_panel(tmp_path, body):
    import ezdxf
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        r = _export(d)
        assert r.returncode == 0, r.stderr
    files = sorted(p.name for p in a.glob("*.dxf"))
    assert files == sorted(f"{n}.dxf" for n in body.panels)
    for f in files:
        assert (a / f).read_bytes() == (b / f).read_bytes(), f
    doc = ezdxf.readfile(str(a / "deck-front.dxf" if (a / "deck-front.dxf").exists()
                             else a / files[0]))
    layers = {e.dxf.layer for e in doc.modelspace()}
    assert layers <= {"CUT", "ENGRAVE"} and "CUT" in layers and "ENGRAVE" in layers
    for f in files:
        doc = ezdxf.readfile(str(a / f))
        xs, ys = [], []
        for e in doc.modelspace().query("LWPOLYLINE"):
            for x, y, *_ in e.get_points():
                xs.append(x)
                ys.append(y)
        assert min(xs) >= -1e-6 and min(ys) >= -1e-6, f
        assert max(xs) <= L.LASER_BED[0] and max(ys) <= L.LASER_BED[1], f


@pytest.mark.slow
def test_export_thickness_and_kerf_override(tmp_path):
    r = _export(tmp_path, "--thickness", "2.7", "--kerf", "0.2")
    assert r.returncode == 0, r.stderr
    assert "2.7 mm" in r.stdout and "kerf 0.2" in r.stdout
    assert len(list(tmp_path.glob("*.dxf"))) >= 25


def test_assembly_laser_registered():
    assert B.assembly("laser", 0.0, 0.0)


# --- R19 feet, R20 nuts ----------------------------------------------------------------

def test_feet_stand_below_the_floor_screw_heads(lay, body):
    """R19: the box stands on four rubber feet; every screw head under the
    floor is above the feet's contact plane, and nothing else reaches it."""
    items = P.assembly(0.0, 0.0)
    feet = [s for n, s, _ in items if n.startswith("hw:foot-")]
    assert len(feet) == 4
    plane = min(s.BoundingBox().zmin for s in feet)
    assert plane == pytest.approx(-P.FOOT_H)
    heads = [s for n, s, _ in items if n.startswith("hw:head-base")]
    low = min(s.BoundingBox().zmin for s in heads)
    assert low < 0.0                                       # there are heads under the floor
    assert low >= plane + P.FOOT_CLEAR - 1e-9
    for n, s, _ in items:
        if not n.startswith("hw:foot-"):
            assert s.BoundingBox().zmin > plane + 1e-6, n
    # engraved locating circles on the floor, one per foot
    floor = [p for n, p in body.panels.items() if n.startswith("base-floor-")]
    for x, y in P.feet(lay):
        assert any(any(abs(sum(u for u, _ in m[:-1]) / (len(m) - 1) - x) < 1e-6
                       and abs(sum(v for _, v in m[:-1]) / (len(m) - 1) - y) < 1e-6
                       for m in p.marks) for p in floor), (x, y)
    hw = P.hardware(lay, WALL)
    assert hw[f"{P.FOOT_D:g} x {P.FOOT_H:g} mm self-adhesive rubber foot"] == 4
    assert any(k.startswith("hook-and-loop tape") for k in hw)


def test_every_tslot_nut_is_a_keepout_in_the_assembly(body):
    """R20: each T-slot's square nut is in the assembly as an ``hw:nut``
    solid of its real size, standing (NUT_W - t) / 2 proud of each face of the
    panel it is in, so the clash tests check it against the drawer, the
    runners and everything else."""
    items = P.assembly(0.0, 0.0)
    nuts = {tuple(round(v, 6) for v in s.BoundingBox().center.toTuple())
            for n, s, _ in items if n.startswith("hw:nut-")}
    assert len(nuts) == len(body.screws)
    proud = (J.NUT_W - WALL) / 2
    for sc in body.screws:
        b = sc.nut
        c = ((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, (b.z0 + b.z1) / 2)
        if sc.frame == "base":                    # base items are not moved
            assert tuple(round(v, 6) for v in c) in nuts
        assert sorted(b.size) == pytest.approx([J.NUT_T, J.NUT_W, J.NUT_W])
        into = body.panel_at(sc.into, sc.at)
        lo, hi = {"x": (b.x0, b.x1), "y": (b.y0, b.y1), "z": (b.z0, b.z1)}[into.normal]
        assert into.z0 - lo == pytest.approx(proud) and hi - (into.z0 + WALL) == pytest.approx(proud)


@pytest.mark.slow
@pytest.mark.parametrize("angle", range(10, 100, 10))
def test_laser_assembly_intermediate_lid_angles_have_no_intersections(angle):
    """The lid's whole swing, not just shut and fully open (finding 7)."""
    assert clashes(B.assembly("laser", float(angle), 0.0), P.DECLARED_OVERLAPS) == []


def test_laser_lid_catch_hole_and_blocks(lay):
    """R22: the lid's magnet goes through a hole in the band face, behind which
    its block is glued; the base's block sits under the front panel's top edge."""
    from demobox.laser import fittings as F
    body = P.build(lay, lay.wall, P.KERF)
    face = body.panels["lid-band-face"]
    for c in lay.lid_catch:
        m = lay.catch_lid_magnet(c)
        assert (m.cx, m.cy, P.MAGNET_D) in face.holes
        blk = F.catch_lid_block_box(lay, c, lay.wall)
        assert blk.z0 == pytest.approx(lay.wall)           # behind the face, not in it
    parts = {k[0] for k in body.placed}
    assert {"catch-block-base", "catch-block-lid"} <= parts
    assert F.hardware(lay, lay.wall)["6 x 3 mm disc magnet"] == 2 + 2 * len(lay.lid_catch)
