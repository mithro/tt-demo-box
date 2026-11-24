"""The laser-cut route (``layout(3.0)``): glued, finger-jointed 3 mm plywood,
printed hinge blocks and magnet blocks, no screws or nuts (spec Decision 9)."""

import importlib.util
import math
from pathlib import Path

import cadquery as cq
import pytest
from shapely.geometry import box as sbox

from demobox import layout as L
from demobox.clash import clashes
from demobox.geom import BedOverflow, box_gap, overlaps
from demobox.laser import fittings as F
from demobox.laser import joints as J
from demobox.laser import panels as P
from demobox.parts.board import BOARD_KEYS
from demobox.printed import body as B
from demobox.shared import hinge as H

ROOT = Path(__file__).resolve().parent.parent
WALL = L.ROUTES["laser"]

BASE = ("base-floor", "base-front", "base-back", "base-left", "base-right")
PLINTH = ("plinth-top", "plinth-front", "plinth-back", "plinth-left", "plinth-right")
LID = ("lid-top", "lid-front", "lid-back", "lid-left", "lid-right")


@pytest.fixture(scope="module")
def lay():
    return L.layout(WALL)


@pytest.fixture(scope="module")
def body(lay):
    return P.build(lay, WALL, P.KERF)


@pytest.fixture(scope="module")
def thin():
    """Plywood sold as 3 mm measuring 2.7, and a wider kerf."""
    return P.build(L.layout(2.7), 2.7, 0.2)


@pytest.fixture(scope="module")
def parts(lay):
    return F.printed_parts(lay, WALL)


def _inside(shape, p) -> bool:
    return shape.isInside(cq.Vector(*p), 1e-4)


def _common(a, b) -> float:
    return a.intersect(b).Volume()


def _solid_box(b) -> cq.Solid:
    return cq.Solid.makeBox(*b.size, cq.Vector(b.x0, b.y0, b.z0))


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
    with that taken off, the two sets of fingers tile the edge."""
    male = _fingers(J.finger_edge(length, t, kerf, True), t)
    female = _fingers(J.finger_edge(length, t, kerf, False), t)
    n = J.finger_count(length, t)
    assert len(male) == (n + 1) // 2 and len(female) == (n - 1) // 2
    k = kerf / 2
    assert male[0][0] == pytest.approx(-k) and male[-1][1] == pytest.approx(length + k)
    nominal = sorted([(a + k, b - k) for a, b in male] + [(a + k, b - k) for a, b in female])
    nominal[0] = (0.0, nominal[0][1])
    nominal[-1] = (nominal[-1][0], length)
    assert sum(b - a for a, b in nominal) == pytest.approx(length)
    for (_, b0), (a1, _) in zip(nominal, nominal[1:]):
        assert a1 == pytest.approx(b0)
    ys = {round(y, 9) for _, y in J.finger_edge(length, t, kerf, True)}
    assert ys == {round(-k, 9), round(t - k, 9)}


def test_finger_segments_are_complementary():
    male = J.finger_segments(100.0, 3.0, True)
    female = J.finger_segments(100.0, 3.0, False)
    both = sorted(male + female)
    assert both[0][0] == 0.0 and both[-1][1] == 100.0
    assert sum(b - a for a, b in both) == pytest.approx(100.0)


# --- no fasteners (spec Goal 3, Decision 9) --------------------------------------------

def test_no_screws_or_nuts(lay):
    assert not hasattr(P, "Screw")
    for name in ("tslot", "nut_pocket", "TSLOT_SCREW", "NUT_W", "NUT_T", "SLOT_W"):
        assert not hasattr(J, name), name
    assert "screws" not in P.LaserBody.__dataclass_fields__
    for key in F.hardware(lay, WALL):
        for word in ("M3", "nut", "screw", "insert", "feet", "foot"):
            assert word.lower() not in key.lower(), key


def test_hardware_exact(lay):
    rod = H.pin_length(lay)
    assert F.hardware(lay, WALL) == {
        "6 x 3 mm disc magnet": 4,
        f"3 mm rod x {rod:.0f} mm (hinge pin)": 1,
        "3 mm rod x 10 mm (board pins, MT2 + loose MT1)": 2,
        "wood glue": 1,
        "double-sided foam tape (VHB type), monitor back and boost module": 1,
    }
    assert lay.boost_in_lid
    # R22/R24: from the first knuckle's blind end (156.5 + 1.0) to x 198.9
    assert f"{rod:.0f}" == "41"


# --- panels -----------------------------------------------------------------------

def test_panel_set(body, lay):
    assert lay.plinth.z1 > lay.plinth.z0
    assert set(body.panels) == set(BASE + PLINTH + LID)
    assert body.seams == ()


def test_every_panel_is_one_valid_piece(body):
    for name, p in body.panels.items():
        assert p.shape.geom_type == "Polygon" and p.shape.is_valid, name
        s = p.solid()
        assert len(s.Solids()) == 1 and s.isValid(), name
        bb = s.BoundingBox()
        assert min(bb.xlen, bb.ylen, bb.zlen) == pytest.approx(p.t), name


@pytest.mark.parametrize("which", ["body", "thin"])
def test_panels_fit_bed(which, body, thin):
    """Every panel, kerf included, fits the 300 x 200 laser bed whole: no
    panel of the compact box needs a seam."""
    b = body if which == "body" else thin
    assert b.seams == ()
    for name, p in b.panels.items():
        w, h = sorted(p.cut_size(), reverse=True)
        assert w <= L.LASER_BED[0] + 1e-6 and h <= L.LASER_BED[1] + 1e-6, (name, w, h)


def test_a_smaller_bed_splits_on_a_glued_finger_seam(lay):
    """Decision 9: a panel over the bed is split along a glued finger seam
    (``_split``): each piece fits, the two make the whole."""
    bed = (190.0, 150.0)
    b = P.build(lay, WALL, P.KERF, bed=bed)
    assert {s.name for s in b.seams} >= {"base-floor", "lid-top"}
    for s in b.seams:
        p0, p1 = (b.panels[n] for n in s.pieces)
        assert p0.shape.intersection(p1.shape).area == pytest.approx(0.0, abs=1e-6)
        assert p0.shape.union(p1.shape).area == pytest.approx(s.whole.area, rel=1e-9)
        assert len(s.runs) >= 1 and all(len(r) >= 3 for r in s.runs)
    for name, p in b.panels.items():
        w, h = sorted(p.cut_size(), reverse=True)
        assert w <= bed[0] + 1e-6 and h <= bed[1] + 1e-6, (name, w, h)


def test_bed_overflow_names_the_panel_and_its_size(lay):
    with pytest.raises(BedOverflow, match=r"[a-z-]+ \d+\.\d\d x \d+\.\d\d mm does not fit the "
                                          r"60 x 40 mm laser bed"):
        P.build(lay, WALL, P.KERF, bed=(60.0, 40.0))


def test_t_must_match_the_layout(lay):
    with pytest.raises(ValueError, match="layout"):
        P.panels(lay, t=2.7)


def test_every_edge_jointed(body):
    """Each pair of panels that touch (their slabs meet or overlap) is
    joined by a declared finger ``Joint``: every glued edge is fingered."""
    joined = {frozenset((j.a, j.b)) for j in body.joints}
    sl = body.slab_panels
    names = sorted(sl)
    touching = set()
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if sl[a].frame == sl[b].frame and box_gap(sl[a].box(), sl[b].box()) <= 1e-6:
                touching.add(frozenset((a, b)))
    assert touching == joined
    for j in body.joints:
        assert j.runs and all(len(r) >= 3 for r in j.runs), (j.a, j.b)


@pytest.mark.slow
@pytest.mark.parametrize("which", ["body", "thin"])
def test_every_joint_is_complementary(which, body, thin):
    """Every jointed pair: the segments tile the zone, ownership alternates
    within a finger run, the male owns both ends, and in 3D the zone is filled
    exactly once (the fingers interlock without overlap or gap)."""
    b = body if which == "body" else thin
    solids = {n: p.solid(holes=False) for n, p in b.slab_panels.items()}
    boxes = {n: p.box() for n, p in b.slab_panels.items()}
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
        for s0, s1, owner in j.segments:
            sb = j.segment_box(s0, s1)
            # the owner has the whole segment, less its own feature cuts
            # (in its plane; the zone spans its thickness)
            u, v = P.PLANE[b.slab_panels[owner].normal]
            rect = sbox(*(getattr(sb, f"{u}0"), getattr(sb, f"{v}0"),
                          getattr(sb, f"{u}1"), getattr(sb, f"{v}1")))
            want = rect.difference(b.slab_cuts[owner]).area * b.t
            got = solids[owner].intersect(_solid_box(sb)).Volume()
            assert got == pytest.approx(want, abs=1e-2), (j.a, j.b, s0, owner)
            for n, s in solids.items():
                if n != owner and b.slab_panels[n].frame == j.frame and overlaps(boxes[n], sb):
                    assert s.intersect(_solid_box(sb)).Volume() <= 1e-3, (j.a, j.b, s0, n)


def test_kerf_is_added_to_every_cut_edge(thin):
    """The cut path is the nominal outline grown kerf/2; holes shrink by kerf."""
    k = 0.2
    for name, p in thin.panels.items():
        back = p.cut_shape().buffer(-k / 2, join_style=2)
        assert back.symmetric_difference(p.shape).area < 1e-3 * p.shape.length, name
        for (u, v, d), (cu, cv, cd) in zip(p.holes, p.cut_holes()):
            assert (cu, cv) == (u, v) and cd == pytest.approx(d - k)


# --- the cache and the body record --------------------------------------------------

def test_cache_key_is_layout():
    """Review fix (R27): the build cache keys on the whole layout, so two
    layouts with the same wall but another bank get their own body."""
    a = L.layout(WALL)
    b = L.layout(WALL, bank="iniu-p512")
    assert a.wall == b.wall and a != b
    ba, bb = P.build(a, WALL, P.KERF), P.build(b, WALL, P.KERF)
    assert ba is not bb
    ha = ba.panels["base-front"].box().z1
    hb = bb.panels["base-front"].box().z1
    assert ha == pytest.approx(a.rim_z) and hb == pytest.approx(b.rim_z) and ha != hb
    assert P.build(a, WALL, P.KERF) is ba                 # still cached


def test_laser_body_is_frozen(body):
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        body.t = 2.0
    with pytest.raises(TypeError):
        body.panels["x"] = body.panels["base-front"]


# --- DXF -----------------------------------------------------------------------------

def _export_module():
    spec = importlib.util.spec_from_file_location("export_laser",
                                                  ROOT / "scripts" / "export_laser.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_dxf_layers(body, tmp_path):
    """Every panel's DXF has only the CUT and ENGRAVE layers, both used, and
    lies within the bed from the origin."""
    import ezdxf
    ex = _export_module()
    for name, p in body.panels.items():
        path = tmp_path / f"{name}.dxf"
        ex.write_dxf(p, path)
        doc = ezdxf.readfile(str(path))
        layers = {e.dxf.layer for e in doc.modelspace()}
        assert layers == {"CUT", "ENGRAVE"}, (name, layers)
        xs, ys = [], []
        for e in doc.modelspace().query("LWPOLYLINE[layer=='CUT']"):
            for x, y, *_ in e.get_points():
                xs.append(x)
                ys.append(y)
        assert min(xs) >= -1e-6 and min(ys) >= -1e-6, name
        assert max(xs) <= L.LASER_BED[0] and max(ys) <= L.LASER_BED[1], name


# --- the plinth and the board pins ------------------------------------------------------

def test_plinth_top_has_the_pin_holes(body, lay):
    """MT2's rod is glued in, each revision's MT1 takes the loose rod: a
    hole in plinth-top at every pin, PEG_DIA across."""
    top = body.panels["plinth-top"]
    s = top.solid()
    assert top.box().z1 == pytest.approx(lay.plinth.z1)
    zm = lay.plinth.z1 - WALL / 2
    for key, p in lay.pins.items():
        assert not _inside(s, (p.cx, p.cy, zm)), key
        assert not _inside(s, (p.cx + L.PEG_DIA / 2 - 0.05, p.cy, zm)), key
        assert _inside(s, (p.cx + L.PEG_DIA / 2 + 0.3, p.cy, zm)), key
    assert len(top.holes) == len(lay.pins)


def test_plinth_walls_leave_a_web_by_the_pin_holes(body, lay):
    """The walls (and their mortises in the top) stay a panel thickness
    clear of every pin hole: the front wall comes in behind the MT1 holes."""
    for n in PLINTH[1:]:
        b = body.slab_panels[n].box()
        for key, p in lay.pins.items():
            dx = max(b.x0 - p.cx, 0.0, p.cx - b.x1)
            dy = max(b.y0 - p.cy, 0.0, p.cy - b.y1)
            assert math.hypot(dx, dy) >= P.PIN_HOLE_D / 2 + WALL - 1e-6, (n, key)
    assert body.slab_panels["plinth-front"].box().y0 > lay.plinth.y0     # set back


def test_plinth_relief_is_clear(body, lay):
    """R7: nothing of the plinth's panels is in ``plinth_relief``."""
    rb = _solid_box(lay.plinth_relief)
    for n in PLINTH:
        assert _common(body.panels[n].solid(), rb) < 1e-6, n


def test_plinth_stands_on_the_floor(body, lay):
    """The plinth's walls are tabbed into the floor and the top (glued), its
    top at the PCB underside."""
    joined = {frozenset((j.a, j.b)) for j in body.joints}
    for n in ("plinth-front", "plinth-back", "plinth-left", "plinth-right"):
        assert frozenset((n, "base-floor")) in joined, n
        assert frozenset((n, "plinth-top")) in joined, n
    assert body.panels["plinth-top"].box().z1 == pytest.approx(lay.board_origin[2])


# --- the hinge --------------------------------------------------------------------------

def test_hinge_blocks_fill_the_plywood_cut_outs(body, lay, parts):
    """The back and right walls are cut away round the hinge; the printed
    knuckle blocks fill those cut-outs flush with the outside faces
    (``panels.hinge_cutouts``)."""
    cut = P.hinge_cutouts(lay, WALL)
    kb, kl = parts["knuckles-base"].solid, parts["knuckles-lid"].solid
    for frame, boxes, solid in (("base", cut["base"], kb), ("lid", cut["lid"], kl)):
        for bx in boxes:
            for n, p in body.panels.items():
                if p.frame == frame:
                    assert _common(p.solid(), _solid_box(bx)) < 1e-6, (n, bx)
        bb = solid.BoundingBox()
        o = lay.outer if frame == "base" else lay.lid_outer
        assert bb.xmax == pytest.approx(o.x1) and bb.ymax == pytest.approx(o.y1)
    hy, hz = lay.hinge_axis
    rr = lay.hinge_relief_r
    # the base block is solid at the outside corner below the relief ...
    assert _inside(kb, (lay.outer.x1 - 0.1, lay.outer.y1 - 0.1, hz - rr - 1.0))
    # ... and in the back wall's place at the notch, below the rim (R26)
    n = lay.hinge_notch
    assert _inside(kb, ((n.x0 + n.x1) / 2, lay.outer.y1 - WALL / 2, hz - 1.0))


def test_knuckles_and_stop_are_in_the_blocks(lay, parts):
    hy, hz = lay.hinge_axis
    kb, kl = parts["knuckles-base"].solid, parts["knuckles-lid"].solid
    for k in H.knuckle_plan(lay):
        xm = (k.x0 + k.x1) / 2
        if k.part == "base":
            assert _inside(kb, (xm, hy - 2.5, hz - 2.5)), k
        else:
            assert _inside(kl, (xm, -2.5, 2.5)), k                     # lid frame
            assert not _inside(kb, (xm, hy - 2.5, hz - 2.5)), k        # relieved
    for s in H.stop_faces(lay):
        ys = [y for y, _ in s.block]
        zs = [z for _, z in s.block]
        p = ((s.x0 + s.x1) / 2, sum(ys) / len(ys), sum(zs) / len(zs))
        assert _inside(kb, p), s


def test_rod_press_fit_only_in_the_lid_block(lay, parts):
    rod = B._rod(lay)
    assert _common(rod, parts["knuckles-base"].solid) < 1e-3
    ring = math.pi * ((L.PIN_ROD_D / 2) ** 2 - (H.PRESS_D / 2) ** 2) * H.PRESS_LEN
    lid_block = parts["knuckles-lid"].solid.moved(lay.lid_location(0.0))
    assert _common(rod, lid_block) == pytest.approx(ring, rel=0.05)


# --- printed fittings ----------------------------------------------------------------------

def test_printed_parts(parts):
    """Decision 9: the printed parts are the hinge (knuckle blocks, seal
    bead) and the magnet blocks; the rest is plywood."""
    assert set(parts) == {"knuckles-base", "knuckles-lid", "seal-bead", "magnet-block"}
    for name, p in parts.items():
        assert len(p.solid.Solids()) == 1 and p.solid.isValid(), name
        assert p.note, name
        bb = B.posed(p).BoundingBox()
        assert bb.xlen <= L.PRINT_BED[0] and bb.ylen <= L.PRINT_BED[1], name
    assert "4" in parts["magnet-block"].note


def test_magnet_block_pocket(parts):
    s = parts["magnet-block"].solid
    bb = s.BoundingBox()
    assert (bb.xlen, bb.ylen, bb.zlen) == pytest.approx((L.CATCH_BLOCK, L.CATCH_BLOCK,
                                                         L.CATCH_BLOCK_H))
    c = (bb.xmin + bb.xlen / 2, bb.ymin + bb.ylen / 2)
    depth = L.MAGNET_T + L.MAGNET_RECESS
    assert not _inside(s, (*c, bb.zmax - depth + 0.1))
    assert _inside(s, (*c, bb.zmax - depth - 0.1))


# --- the assembly -----------------------------------------------------------------------

def _shut():
    return F.assembly(0.0, False)


def test_assembly_parts(lay):
    names = [n for n, _, _ in _shut()]
    assert len(names) == len(set(names))
    want = set(BASE + PLINTH + LID)
    want |= {"knuckles-base", "knuckles-lid", "seal-bead", "board", "tinyvga", "vga-plug",
             "monitor", "bank", "hw:hinge-rod", "hw:board-pin-mt2", "hw:board-pin-mt1"}
    want |= {f"magnet-block-{s}-{i}" for s in ("base", "lid") for i in (1, 2)}
    want |= {f"hw:catch-magnet-{s}-{i}" for s in ("base", "lid") for i in (1, 2)}
    if lay.boost_in_lid:
        want.add("boost")
    assert set(names) == want


def test_assembly_through_the_shared_entry_point():
    """``printed.body.assembly("laser", ...)`` forwards to this route, the
    bank too."""
    d = {n: s for n, s, _ in B.assembly("laser", 0.0, False, bank="iniu-p512")}
    assert d["bank"].BoundingBox().xlen == pytest.approx(104.0)
    assert d["base-front"].BoundingBox().zmax == pytest.approx(
        L.layout(WALL, bank="iniu-p512").rim_z)


def test_nothing_proud(lay):
    """Shut, every part is within the base's outline and the closed lid's."""
    o = lay.outer
    top = lay.hinge_axis[1] + lay.lid_outer.z1
    for name, s, _ in _shut():
        bb = s.BoundingBox()
        assert bb.xmin >= o.x0 - 1e-6 and bb.xmax <= o.x1 + 1e-6, (name, bb.xmin, bb.xmax)
        assert bb.ymin >= o.y0 - 1e-6 and bb.ymax <= o.y1 + 1e-6, (name, bb.ymin, bb.ymax)
        assert bb.zmin >= o.z0 - 1e-6 and bb.zmax <= top + 1e-6, (name, bb.zmin, bb.zmax)


def test_board_pins_stand_proud_of_the_board(lay):
    d = {n: s for n, s, _ in _shut()}
    for key, n in (("MT2", "hw:board-pin-mt2"), (f"{F.ASSEMBLY_BOARD}/MT1", "hw:board-pin-mt1")):
        bb = d[n].BoundingBox()
        p = lay.pins[key]
        assert bb.zmax == pytest.approx(p.z1)
        assert bb.zlen == pytest.approx(F.BOARD_PIN_LEN)
        assert bb.zmin < lay.plinth.z1 - WALL                 # right through the plinth top


def test_assembly_bank_out_is_lifted(lay):
    out = {n: s for n, s, _ in F.assembly(L.LID_OPEN_DEG, True)}
    assert out["bank"].BoundingBox().zmin == pytest.approx(lay.rim_z + B.BANK_OUT_LIFT)


def test_only_the_press_fit_is_declared():
    assert P.DECLARED_OVERLAPS == frozenset({frozenset(("hw:hinge-rod", "knuckles-lid"))})


def _cases():
    out = [(rev, float(a), False) for rev in BOARD_KEYS for a in range(0, 101, 10)]
    out += [(rev, L.LID_OPEN_DEG, True) for rev in BOARD_KEYS]
    return out


@pytest.mark.slow
@pytest.mark.parametrize("rev,angle,bank_out", _cases(),
                         ids=[f"{r}-{a:g}{'-bank-out' if o else ''}" for r, a, o in _cases()])
def test_assembly_no_clash(rev, angle, bank_out):
    """Nothing interpenetrates but the one declared pair, the rod in the lid
    knuckle block's R24 press fit."""
    items = F.assembly(angle, bank_out, board=rev)
    assert clashes(items, P.DECLARED_OVERLAPS) == []
