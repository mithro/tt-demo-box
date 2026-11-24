"""The 3D-printed route (``layout(2.4)``): base, lid, loose pin, assembly."""

import math

import cadquery as cq
import pytest

from demobox import checks as C
from demobox import layout as L
from demobox.clash import clashes
from demobox.geom import BedOverflow
from demobox.parts.board import BOARD_KEYS
from demobox.printed import body as B
from demobox.shared import hinge as H
from demobox.shared import pin as P


@pytest.fixture(scope="module")
def lay():
    return L.layout(L.ROUTES["printed"])


@pytest.fixture(scope="module")
def parts(lay):
    return B.printed_parts(lay)


@pytest.fixture(scope="module")
def base(lay):
    return B.base(lay)


@pytest.fixture(scope="module")
def lid(lay):
    return B.lid(lay)


def _inside(shape, p) -> bool:
    return shape.isInside(cq.Vector(*p), 1e-4)


def _common(a, b) -> float:
    return a.intersect(b).Volume()


def _box(x0, y0, z0, x1, y1, z1) -> cq.Solid:
    return cq.Solid.makeBox(x1 - x0, y1 - y0, z1 - z0, cq.Vector(x0, y0, z0))


def _rod(lay) -> cq.Solid:
    hy, hz = lay.hinge_axis
    length = H.pin_length(lay)
    return cq.Solid.makeCylinder(L.PIN_ROD_D / 2, length,
                                 cq.Vector(lay.outer.x1 - length, hy, hz), cq.Vector(1, 0, 0))


def _in_lid_frame(lay, p):
    """A base-frame point of the closed box, in the lid frame."""
    hy, hz = lay.hinge_axis
    return (p[0], p[1] - hy, p[2] - hz)


# --- the parts list and the bed -------------------------------------------------

def test_parts_are_single_valid_solids(parts):
    assert set(parts) == {"base", "lid", "mt1-pin"}
    for name, p in parts.items():
        assert len(p.solid.Solids()) == 1, name
        assert p.solid.isValid(), name
        assert p.note, name


def test_parts_fit_the_bed(parts):
    """Each footprint is within 220 x 220 in its print orientation, lying on
    a flat face at Z = 0."""
    for name, p in parts.items():
        bb = B.posed(p).BoundingBox()
        assert (bb.xmin, bb.ymin, bb.zmin) == pytest.approx((0, 0, 0), abs=1e-6), name
        assert bb.xlen <= L.PRINT_BED[0] + 1e-6 and bb.ylen <= L.PRINT_BED[1] + 1e-6, \
            (name, bb.xlen, bb.ylen)
        assert B.bed_contact_area(B.posed(p)) > 0, name


def test_print_orientations(parts, lay):
    """The base prints floor down, the lid top plate down, the pin standing."""
    o, lo, w = lay.outer, lay.lid_outer, lay.wall
    base = B.posed(parts["base"])
    assert B.bed_contact_area(base) == pytest.approx(o.size[0] * o.size[1], rel=1e-3)
    lid = B.posed(parts["lid"])
    assert B.bed_contact_area(lid) == pytest.approx(lo.size[0] * lo.size[1], rel=1e-3)
    bb = lid.BoundingBox()
    assert _inside(lid, (bb.xlen / 2, bb.ylen / 2, w / 2))              # the top plate
    assert not _inside(lid, (bb.xlen / 2, bb.ylen / 2, w + 1.0))         # the tray, open up
    pin = B.posed(parts["mt1-pin"]).BoundingBox()
    assert pin.zlen > pin.xlen                                            # standing


def test_oversized_part_raises_bed_overflow(parts):
    with pytest.raises(BedOverflow, match=r"base 197\.70 x 174\.76 mm"):
        B.check_bed("base", B.posed(parts["base"]), (150.0, 220.0))


# --- hardware ---------------------------------------------------------------------

def test_hardware_exact(lay):
    rod = H.pin_length(lay)
    assert B.hardware(lay) == {
        "6 x 3 mm disc magnet": 4,
        "3 mm rod x 40.8 mm (hinge pin; steel, or 2.85 mm filament)": 1,
        "double-sided foam tape (VHB type), monitor back and boost module": 1,
    }
    assert f"{rod:.1f}" == "40.8"     # R24: 156.9 .. 197.7


def test_no_fasteners_anywhere(lay):
    for key in B.hardware(lay):
        for word in ("M3", "screw", "nut", "insert"):
            assert word.lower() not in key.lower(), key


# --- nothing proud ----------------------------------------------------------------

def test_nothing_proud(lay):
    """Review Focus 5: shut, every part's bounding box is within the base's
    outline united with the closed lid's."""
    o = lay.outer
    top = lay.hinge_axis[1] + lay.lid_outer.z1
    for name, s, _ in B.assembly("printed", 0.0, False):
        bb = s.BoundingBox()
        assert bb.xmin >= o.x0 - 1e-6 and bb.xmax <= o.x1 + 1e-6, (name, bb.xmin, bb.xmax)
        assert bb.ymin >= o.y0 - 1e-6 and bb.ymax <= o.y1 + 1e-6, (name, bb.ymin, bb.ymax)
        assert bb.zmin >= o.z0 - 1e-6 and bb.zmax <= top + 1e-6, (name, bb.zmin, bb.zmax)


# --- the catch ---------------------------------------------------------------------

def _pocket_checks(solid, c, open_z, into):
    """A pocket ``MAGNET_D + 0.2`` across and ``MAGNET_T + MAGNET_RECESS``
    deep from the face at ``open_z``, going ``into`` (+1 up, -1 down)."""
    r = (L.MAGNET_D + 0.2) / 2
    depth = L.MAGNET_T + L.MAGNET_RECESS
    for dz in (0.1, depth / 2, depth - 0.1):
        z = open_z + into * dz
        assert not _inside(solid, (c.cx, c.cy, z))
        assert not _inside(solid, (c.cx + r - 0.05, c.cy, z))
        assert _inside(solid, (c.cx + r + 0.05, c.cy, z))
    assert _inside(solid, (c.cx, c.cy, open_z + into * (depth + 0.1)))   # its floor


def test_magnet_pockets_flush(lay, base, lid):
    """Two pockets each side, open at the seam; the magnet in each sits
    MAGNET_RECESS under the face, nothing proud."""
    for c in lay.lid_catch:
        assert c.z1 == pytest.approx(lay.rim_z - L.MAGNET_RECESS)
        _pocket_checks(base, c, lay.rim_z, -1)
        m = lay.catch_lid_magnet(c)
        assert m.z0 == pytest.approx(L.MAGNET_RECESS)
        _pocket_checks(lid, m, 0.0, +1)


# --- the plinth and pins -------------------------------------------------------------

def _plinth_samples(lay, step=5.0):
    pl, rl = lay.plinth, lay.plinth_relief
    pins = list(lay.pins.values())
    x = pl.x0 + 0.5
    while x < pl.x1:
        y = pl.y0 + 0.5
        while y < pl.y1:
            near_pin = any(math.hypot(x - p.cx, y - p.cy) < L.PEG_HOLE_D / 2 + 0.3 for p in pins)
            in_relief = rl.x0 - 0.3 < x < rl.x1 + 0.3 and rl.y0 - 0.3 < y < rl.y1 + 0.3
            if not near_pin and not in_relief:
                yield x, y
            y += step
        x += step


def test_plinth_top_level(lay, base):
    """The plinth's top is one flat face at the PCB underside: solid a full
    wall thick under it, and nothing above it but the MT2 pin."""
    pl = lay.plinth
    assert pl.z1 == pytest.approx(lay.board_origin[2])
    for x, y in _plinth_samples(lay):
        assert _inside(base, (x, y, pl.z1 - 0.1)), (x, y)
        assert _inside(base, (x, y, pl.z1 - lay.wall + 0.1)), (x, y)
        assert not _inside(base, (x, y, pl.z1 + 0.1)), (x, y)
    faces = [f for f in base.Faces() if f.geomType() == "PLANE"
             and abs(f.BoundingBox().zmin - pl.z1) < 1e-6
             and abs(f.BoundingBox().zmax - pl.z1) < 1e-6]
    assert len(faces) == 1
    bb = faces[0].BoundingBox()
    assert (bb.xmin, bb.ymin, bb.xmax, bb.ymax) == pytest.approx((pl.x0, pl.y0, pl.x1, pl.y1))


def test_plinth_relief_keeps_a_wall_under_it(lay, base):
    r = lay.plinth_relief
    cx, cy = (max(r.x0, lay.plinth.x0) + r.x1) / 2, (r.y0 + r.y1) / 2
    assert not _inside(base, (cx, cy, r.z0 + 0.1))
    assert _inside(base, (cx, cy, r.z0 - 0.1))
    assert _inside(base, (cx, cy, r.z0 - lay.wall + 0.1))


def test_plinth_is_solid(lay, base):
    """R27: the plinth is solid (a slicer's infill saves the filament; an
    enclosed void would trap supports): the base is one shell."""
    assert len(base.Shells()) == 1
    pl = lay.plinth
    for fx, fy in ((0.3, 0.3), (0.5, 0.5), (0.7, 0.4)):
        x, y = pl.x0 + fx * pl.size[0], pl.y0 + fy * pl.size[1]
        assert _inside(base, (x, y, (pl.z0 + pl.z1) / 2)), (x, y)


def test_base_follows_the_layout():
    """R27: a different kit builds its own base, never the cached design one."""
    design = B.base(L.layout(2.4)).BoundingBox()
    other_lay = L.layout(2.4, bank="iniu-p512")
    other = B.base(other_lay).BoundingBox()
    # the INIU is lower (29 vs 32 mm), so its base's rim is lower
    assert other_lay.rim_z < L.layout(2.4).rim_z
    assert (other.xlen, other.ylen, other.zlen) != pytest.approx(
        (design.xlen, design.ylen, design.zlen))
    assert (other.xlen, other.ylen) == pytest.approx(other_lay.outer.size[:2])
    assert other.zlen < design.zlen
    shut = {n: s for n, s, _ in B.assembly("printed", 0.0, False, bank="iniu-p512")}
    assert shut["base"].BoundingBox().xlen == pytest.approx(other_lay.outer.size[0])
    assert shut["bank"].BoundingBox().xlen == pytest.approx(104.0)


def test_only_the_press_fit_is_declared():
    """Every other pair must not touch, so none is exempt."""
    assert B.DECLARED_OVERLAPS == frozenset({frozenset(("hw:hinge-rod", "lid"))})


def test_mt1_holes_go_to_the_floor(lay, base):
    depth = P.socket_depth(lay)
    r = L.PEG_HOLE_D / 2
    for rev in BOARD_KEYS:
        p = lay.pins[f"{rev}/MT1"]
        bottom = p.z0 - depth
        assert bottom == pytest.approx(lay.wall)                  # the floor's top
        for z in (bottom + 0.1, (bottom + p.z0) / 2, p.z0 - 0.1):
            assert not _inside(base, (p.cx, p.cy, z)), (rev, z)
            assert not _inside(base, (p.cx + r - 0.05, p.cy, z)), (rev, z)
            assert _inside(base, (p.cx + r + 0.05, p.cy, z)), (rev, z)
        assert _inside(base, (p.cx, p.cy, bottom - 0.1))
        assert not _inside(base, (p.cx, p.cy, p.z0 + 0.5))       # no fixed pin there


def test_mt2_pin_is_integral(lay, base):
    p = lay.pins["MT2"]
    zm = (p.z0 + p.z1) / 2
    assert _inside(base, (p.cx, p.cy, p.z0 + 0.5))
    assert _inside(base, (p.cx, p.cy, p.z1 - 0.1))
    assert _inside(base, (p.cx + p.r - 0.05, p.cy, zm))
    assert not _inside(base, (p.cx + p.r + 0.05, p.cy, zm))
    assert not _inside(base, (p.cx, p.cy, p.z1 + 0.1))


# --- the hinge -------------------------------------------------------------------

def test_knuckles_are_built_in(lay, base, lid):
    """Each knuckle is part of its own part's solid, and the other part is
    cut back there (closed)."""
    hy, hz = lay.hinge_axis
    for k in H.knuckle_plan(lay):
        xm = (k.x0 + k.x1) / 2
        low, high = (xm, hy - 2.5, hz - 2.5), (xm, hy - 2.5, hz + 2.5)
        if k.part == "base":
            assert _inside(base, low) and _inside(base, high), k
            assert not _inside(lid, _in_lid_frame(lay, high)), k
        else:
            assert _inside(lid, _in_lid_frame(lay, low)), k
            assert _inside(lid, _in_lid_frame(lay, high)), k
            assert not _inside(base, low) and not _inside(base, high), k


def test_rod_runs_in_the_bores(lay, base, lid):
    """The rod is a slip fit in the base knuckle, and in the lid knuckles but
    for the last PRESS_LEN, the press fit (R24)."""
    rod = _rod(lay)
    assert _common(rod, base) < 1e-3
    ring = math.pi * ((L.PIN_ROD_D / 2) ** 2 - (H.PRESS_D / 2) ** 2) * H.PRESS_LEN
    assert _common(rod, lid.moved(lay.lid_location(0.0))) == pytest.approx(ring, rel=0.05)


def test_seal_bead_on_the_base(lay, base):
    hy, hz = lay.hinge_axis
    for x0, x1 in H.bead_x(lay):
        assert _inside(base, ((x0 + x1) / 2, hy + 1.0, hz + 2.0))


def test_notch_is_clear(lay, base, lid):
    """The notch is open above the seam (the seal bead's notch, where the
    pigtail passes) in both parts (R26)."""
    n = lay.hinge_notch
    hy, hz = lay.hinge_axis
    xm = (n.x0 + n.x1) / 2
    for dy in (-3.5, 0.0, 2.0, 3.5):
        for dz in (0.5, 3.5):
            p = (xm, hy + dy, hz + dz)
            assert not _inside(base, p), p
            assert not _inside(lid, _in_lid_frame(lay, p)), p


def test_back_wall_solid_below_the_rim_at_the_notch(lay, base):
    """R26: no slot in the base's back wall under the notch (across its X
    range, less the hinge's own relief FIT past a lid knuckle's end)."""
    n, o, w = lay.hinge_notch, lay.outer, lay.wall
    x1 = min([n.x1] + [k.x0 - L.FIT for k in H.knuckle_plan(lay)
                       if k.part == "lid" and k.x0 >= n.x0])
    assert x1 - n.x0 > 0.8 * (n.x1 - n.x0)
    for fx in (0.05, 0.5, 0.95):
        x = n.x0 + fx * (x1 - n.x0)
        for y in (o.y1 - w + 0.1, o.y1 - w / 2, o.y1 - 0.1):
            for z in (lay.rim_z - 0.1, lay.rim_z - 2.0, n.z0 - 0.5):
                assert _inside(base, (x, y, z)), (x, y, z)


# --- the lid --------------------------------------------------------------------------

def test_lid_inside_face_is_flat(lay, lid):
    """No pocket for the monitor, nor for the boost (R25): a flat inside face
    over the whole tray, ``wall`` thick, for the tape."""
    z = lay.lid_outer.z1 - lay.wall
    for b in (lay.monitor_space, lay.lid_strip, lay.boost_pocket):
        for fx in (0.1, 0.5, 0.9):
            for fy in (0.1, 0.5, 0.9):
                x, y = b.x0 + fx * b.size[0], b.y0 + fy * b.size[1]
                assert _inside(lid, (x, y, z + 0.1)), (b.what, x, y)
                assert not _inside(lid, (x, y, z - 0.1)), (b.what, x, y)


# --- what the base must not block -------------------------------------------------------

def _tube(pts, r):
    shapes = [cq.Solid.makeSphere(r, cq.Vector(*p), angleDegrees1=-90, angleDegrees2=90)
              for p in pts]
    for a, b in zip(pts, pts[1:]):
        d = cq.Vector(*b) - cq.Vector(*a)
        if d.Length > 1e-9:
            shapes.append(cq.Solid.makeCylinder(r, d.Length, cq.Vector(*a), d.normalized()))
    return shapes[0].fuse(*shapes[1:]).clean()


@pytest.mark.parametrize("angle", [0.0, L.LID_OPEN_DEG])
@pytest.mark.parametrize("rev", BOARD_KEYS)
def test_pigtail_misses_the_solids(lay, base, lid, angle, rev):
    """``checks.pigtail_path``, swept as a cable-thick (5 mm) tube, misses
    the base and the lid."""
    assert C.PIGTAIL.dia == 5.0
    tube = _tube(C.pigtail_path(lay, angle, rev), C.PIGTAIL.dia / 2)
    assert _common(tube, base) < 1e-3
    assert _common(tube, lid.moved(lay.lid_location(angle))) < 1e-3


def test_bank_lifts_out_of_the_solids(lay, base, lid):
    """At the stop nothing of the base or lid is over the packed bank: its
    footprint, swept up from the bay floor, meets neither."""
    b = C.packed_bank(lay)
    sweep = _box(b.x0, b.y0, b.z0, b.x1, b.y1, lay.rim_z + 200.0)
    assert _common(sweep, base) < 1e-3
    assert _common(sweep, lid.moved(lay.lid_location(L.LID_OPEN_DEG))) < 1e-3


@pytest.mark.parametrize("rev", BOARD_KEYS)
def test_board_seats_on_the_plinth(lay, base, rev):
    """The PCB rests on the plinth (touching, not in it) and the MT2 pin
    passes through its hole."""
    pcb = B.board_pcb(lay, rev)
    assert _common(pcb, base) < 1e-3
    assert _common(pcb.translate(cq.Vector(0, 0, -0.1)), base) > 1.0


# --- the assembly -----------------------------------------------------------------------

def test_assembly_parts(lay):
    names = [n for n, _, _ in B.assembly("printed", 0.0, False)]
    assert len(names) == len(set(names))
    want = {"base", "lid", "mt1-pin", "board", "tinyvga", "vga-plug", "monitor", "bank",
            "hw:hinge-rod"}
    want |= {f"hw:catch-magnet-{s}-{i}" for s in ("base", "lid") for i in (1, 2)}
    if lay.boost_in_lid:
        want.add("boost")
    assert set(names) == want


def test_assembly_bank_out_is_lifted(lay):
    shut = {n: s for n, s, _ in B.assembly("printed", L.LID_OPEN_DEG, False)}
    out = {n: s for n, s, _ in B.assembly("printed", L.LID_OPEN_DEG, True)}
    assert B.BANK_OUT_LIFT == 60.0
    assert out["bank"].BoundingBox().zmin == pytest.approx(lay.rim_z + B.BANK_OUT_LIFT)
    assert shut["bank"].BoundingBox().zmin == pytest.approx(lay.bank_bay.z0)


def test_assembly_lid_turns_about_the_axis(lay):
    shut = {n: s for n, s, _ in B.assembly("printed", 0.0, False)}
    open_ = {n: s for n, s, _ in B.assembly("printed", L.LID_OPEN_DEG, False)}
    for n in ("lid", "monitor"):
        assert shut[n].Volume() == pytest.approx(open_[n].Volume())
    assert open_["lid"].BoundingBox().zmax > shut["lid"].BoundingBox().zmax + 100


def test_assembly_unknown_route():
    with pytest.raises(ValueError, match="unknown route"):
        B.assembly("cardboard", 0.0, False)


def _cases():
    out = [(rev, float(a), False) for rev in BOARD_KEYS for a in range(0, 101, 10)]
    out += [(rev, L.LID_OPEN_DEG, True) for rev in BOARD_KEYS]
    return out


@pytest.mark.slow
@pytest.mark.parametrize("rev,angle,bank_out", _cases(),
                         ids=[f"{r}-{a:g}{'-bank-out' if o else ''}" for r, a, o in _cases()])
def test_assembly_no_clash(rev, angle, bank_out):
    """Review Focus 3/4: nothing interpenetrates but the one declared pair,
    the rod in the lid knuckle's R24 press fit."""
    items = B.assembly("printed", angle, bank_out, board=rev)
    assert clashes(items, B.DECLARED_OVERLAPS) == []
