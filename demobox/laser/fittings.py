"""The laser route's printed fittings, its keep-outs, parts and hardware
lists, and its assembly.

Frames are ``demobox.layout``'s (see ``demobox.laser.panels``).  Every
fitting is glued to the panels it stands against; the screws that the printed
route puts into heat-set inserts go into M3 square nuts in pockets in them:

* ``nut-block-base-leaf`` (4): behind the base back wall at each base hinge
  leaf screw, standing through notches in the deck;
* ``nut-block-lid-leaf`` (2): behind the lid hinge wall, up to the lid back;
* ``nut-block-bezel`` (3): a column in each screwed corner of the lid's
  opening, from the bezel's back to the lid back (``inserts.bezel_screws``);
* ``nut-block-clip`` (1): on the band face in the corner of the lid's left
  wall and the band wall, under the bezel clip's screw (``panels.clip_screws``);
* ``nut-cup-mt2`` (1): under the deck at MT2, the board's screw going down
  through ``standoff-mt2`` and the deck into its nut;
* ``standoff-mt2``, ``deck-support`` (2) and ``mt1-boss``: the board's mounts
  (``Layout.standoffs``/``supports``/``mt1_boss``), glued on the deck's
  engraved outlines; the boss has a PEG_HOLE_D hole per revision for the loose
  ``mt1-pin``;
* ``magnet-block`` (2): the latch, one in the drawer's front corner (magnet
  up), one over it in the base's front corner (the same part upside down).
* ``catch-block-base`` (2), ``catch-block-lid`` (2): the lid catch (R22), two
  places along the front (``Layout.lid_catch``): a block glued inside the
  base's front panel under its top edge, magnet up; a block glued behind the
  lid's band face over it, its magnet pressed into a hole in the face
  (``panels``), the two magnets facing across the seam.

Each nut pocket is NUT_DEPTH from the block's entry face (where the screw
comes in) and runs right through the block across the screw, so the nut goes
in from the side after gluing.
"""

from __future__ import annotations

import math

import cadquery as cq

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox.geom import Box
from demobox.layout import (FIT, INSERT_MATERIAL, MAGNET_D, MAGNET_RECESS, MAGNET_T,
                            PEG_HOLE_D, PRINT_BED, ROUTES, Layout, layout)
from demobox.laser import joints as J
from demobox.laser import panels as P
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS
from demobox.checks import panel_in_lid
from demobox.printed import body as PB
from demobox.shared import hinge as H
from demobox.shared import inserts as I
from demobox.shared import m3
from demobox.shared.packing import battery_packing
from demobox.shared.pin import locating_pin

COLOURS = {"panel": (0.82, 0.66, 0.44), "fitting": (0.30, 0.32, 0.36),
           "magnet": (0.55, 0.55, 0.60)}


def _box(b: Box) -> cq.Solid:
    return cq.Solid.makeBox(*b.size, cq.Vector(b.x0, b.y0, b.z0))


def _cyl(p, d, r, length) -> cq.Solid:
    return cq.Solid.makeCylinder(r, length, cq.Vector(*p), cq.Vector(*d))


def _nut_block(b: Box, at, direction, slot_axis: str) -> cq.Shape:
    """Block ``b`` with an M3 clearance hole along ``direction`` through
    ``at`` (on its entry face) and a square-nut pocket NUT_DEPTH in from that
    face, open right through the block along ``slot_axis``."""
    d = cq.Vector(*direction)
    p = cq.Vector(*at)
    span = max(b.size) + 2.0
    hole = _cyl((p - d * 1.0).toTuple(), direction, m3.CLEARANCE_D / 2, span)
    ax = "xyz"
    da = ax[[abs(v) for v in direction].index(1.0)]
    third = next(a for a in ax if a not in (da, slot_axis))
    n = J.NUT_W / 2 + J.NUT_FIT
    r = {}
    for k, a in enumerate(ax):
        c = p.toTuple()[k]
        if a == da:
            lo, hi = sorted((c + direction[k] * NUT_DEPTH0, c + direction[k] * NUT_DEPTH1))
        elif a == third:
            lo, hi = c - n, c + n
        else:
            lo, hi = P._rng(b, a)[0] - 1.0, P._rng(b, a)[1] + 1.0
        r[a] = (lo, hi)
    pocket = _box(P._mk(r))
    return _box(b).cut(hole, pocket).clean()


NUT_DEPTH0, NUT_DEPTH1 = P.NUT_DEPTH


def _blocks(lay: Layout, t: float) -> dict:
    """Where each glued fitting goes: instance -> (part, frame, Box, screw
    entry point or None, direction, slot axis)."""
    D = lay.outer.y1
    dz = lay.deck_z
    Lz = lay.lid_outer.z1
    nb, nd = P.NUT_BLOCK / 2, P.NUT_BLOCK_D
    out = {}
    for i, (x, z) in enumerate(H.base_leaf_screws(lay)):
        out[f"nut-block-base-leaf-{i + 1}"] = (
            "nut-block-base-leaf", "base", Box(x - nb, D - t - nd, z - nb, x + nb, D - t, z + nb),
            (x, D - t, z), (0.0, -1.0, 0.0), "x")
    for i, (x, z) in enumerate(H.lid_leaf_screws(lay)):
        out[f"nut-block-lid-leaf-{i + 1}"] = (
            "nut-block-lid-leaf", "lid", Box(x - nb, -t - nd, z - nb, x + nb, -t, Lz - t),
            (x, -t, z), (0.0, -1.0, 0.0), "x")
    s = I.BEZEL_SCREW_INSET
    for i, (x, y) in enumerate(I.bezel_screws(lay)):
        out[f"nut-block-bezel-{i + 1}"] = (
            "nut-block-bezel", "lid", Box(x - s, y - s, INSERT_MATERIAL, x + s, y + s, Lz - t),
            (x, y, INSERT_MATERIAL), (0.0, 0.0, 1.0), "x")
    cb = P.CLIP_BLOCK
    for i, (x, y) in enumerate(P.clip_screws(lay, t)):
        out[f"nut-block-clip-{i + 1}" if i else "nut-block-clip"] = (
            "nut-block-clip", "lid", Box(x - cb / 2, y - cb / 2, t, x + cb / 2, y + cb / 2, t + cb),
            (x, y, t), (0.0, 0.0, 1.0), "x")
    c = lay.standoffs[0]
    out["nut-cup-mt2"] = ("nut-cup-mt2", "base",
                          Box(c.cx - P.CUP / 2, c.cy - P.CUP / 2, dz - t - P.CUP_H,
                              c.cx + P.CUP / 2, c.cy + P.CUP / 2, dz - t),
                          (c.cx, c.cy, dz - t), (0.0, 0.0, -1.0), "x")
    return out


def _magnets(lay: Layout, t: float) -> dict:
    """instance -> (frame, block Box, magnet's (x, y, z0), hole facing +1/-1 in z)."""
    d = P._drawer_box(lay)
    rz0, _ = P._runner_z(lay)
    mb = P.MAGNET_BLOCK
    x, y = P._magnet_xy(lay)
    return {
        "magnet-block-drawer": ("drawer", Box(x - mb / 2, y - mb / 2, d.z1 - mb, x + mb / 2,
                                              y + mb / 2, d.z1), (x, y, d.z1 - P.MAGNET_T), 1),
        "magnet-block-base": ("base", Box(x - mb / 2, y - mb / 2, rz0, x + mb / 2, y + mb / 2,
                                          rz0 + mb), (x, y, rz0), -1),
    }


def _magnet_block(b: Box, m, facing) -> cq.Shape:
    hole = _cyl(m, (0, 0, 1), P.MAGNET_D / 2, P.MAGNET_T + (1.0 if facing > 0 else 0.0))
    if facing < 0:
        hole = _cyl((m[0], m[1], m[2] - 1.0), (0, 0, 1), P.MAGNET_D / 2, P.MAGNET_T + 1.0)
    return _box(b).cut(hole).clean()


def catch_lid_block_box(lay: Layout, c, t: float) -> Box:
    """The laser lid's catch block (lid frame): glued behind the band face
    (the magnet sits in a hole through the face), so from ``t`` up."""
    b = lay.catch_lid_block(c)
    return Box(b.x0, b.y0, t, b.x1, b.y1, t + (b.z1 - b.z0), b.what)


def _catch_block(lay: Layout, frame: str, c, t: float) -> cq.Shape:
    """A lid catch block with its magnet pocket open on the seam side.  The
    base's is under its top edge, a full-depth pocket; the lid's stands behind
    the band face, whose hole holds most of the magnet, so its pocket is only
    the magnet's last bit (none if the face is thick enough)."""
    depth = MAGNET_T + MAGNET_RECESS
    if frame == "base":
        b = lay.catch_base_block(c)
        return _box(b).cut(_cyl((c.cx, c.cy, b.z1 - depth), (0, 0, 1), MAGNET_D / 2,
                                depth + 1.0)).clean()
    b, mg = catch_lid_block_box(lay, c, t), lay.catch_lid_magnet(c)
    into = mg.z1 - t
    if into <= 0:
        return _box(b)
    return _box(b).cut(_cyl((mg.cx, mg.cy, t - 1.0), (0, 0, 1), MAGNET_D / 2, into + 1.0)).clean()


def _catch(lay: Layout, t: float) -> dict:
    """instance -> (part, frame, block solid, magnet Cyl in that frame) for the lid catch."""
    out = {}
    for i, c in enumerate(lay.lid_catch, 1):
        out[f"catch-block-base-{i}"] = ("catch-block-base", "base",
                                        _catch_block(lay, "base", c, t), c)
        out[f"catch-block-lid-{i}"] = ("catch-block-lid", "lid", _catch_block(lay, "lid", c, t),
                                       lay.catch_lid_magnet(c))
    return out


def _mounts(lay: Layout) -> dict:
    """The board's printed mounts on the deck: instance -> (part, solid)."""
    out = {}
    for c in lay.standoffs:
        s = _cyl((c.cx, c.cy, c.z0), (0, 0, 1), c.r, c.z1 - c.z0)
        s = s.cut(_cyl((c.cx, c.cy, c.z0 - 1), (0, 0, 1), m3.CLEARANCE_D / 2, c.z1 - c.z0 + 2))
        out["standoff-mt2"] = ("standoff-mt2", s.clean())
    for i, c in enumerate(lay.supports):
        out[f"deck-support-{i + 1}"] = ("deck-support",
                                        _cyl((c.cx, c.cy, c.z0), (0, 0, 1), c.r, c.z1 - c.z0))
    b = lay.mt1_boss
    length = math.hypot(b.x1 - b.x0, b.y1 - b.y0)
    angle = math.degrees(math.atan2(b.y1 - b.y0, b.x1 - b.x0))
    boss = (cq.Workplane("XY", origin=((b.x0 + b.x1) / 2, (b.y0 + b.y1) / 2, b.z0))
            .slot2D(length + 2 * b.r, 2 * b.r, angle).extrude(b.z1 - b.z0).val())
    for pg in lay.pegs.values():
        boss = boss.cut(_cyl((pg.cx, pg.cy, b.z0 - 1), (0, 0, 1), PEG_HOLE_D / 2, b.z1 - b.z0 + 2))
    out["mt1-boss"] = ("mt1-boss", boss.clean())
    return out


def placed(lay: Layout, t: float) -> list[tuple[str, str, str, cq.Shape]]:
    """Every glued fitting where it goes: (part, instance, frame, solid)."""
    out = []
    for inst, (part, frame, b, at, d, slot) in _blocks(lay, t).items():
        out.append((part, inst, frame, _nut_block(b, at, d, slot)))
    for inst, (part, s) in _mounts(lay).items():
        out.append((part, inst, "base", s))
    for inst, (frame, b, m, facing) in _magnets(lay, t).items():
        out.append(("magnet-block", inst, frame, _magnet_block(b, m, facing)))
    for inst, (part, frame, s, _m) in _catch(lay, t).items():
        out.append((part, inst, frame, s))
    return out


def keepouts(lay: Layout, t: float) -> list[tuple[str, Box]]:
    """(frame, Box) that no T-slot nut or screw head may enter: the drawer's
    sweep, the bank, the boost converter, the USB-C cable's drop, the hinge
    channel, the boards and the hinge parts; in the lid, the monitor's insert
    and the bezel."""
    d = P._drawer_box(lay)
    op = P._opening(lay)
    us, ch = lay.usb_slot, lay.hinge_cable_channel
    hz = lay.hinge_axis[1]
    out = [("base", Box(-lay.drawer_travel - 1.0, t, t, d.x1 + FIT, op.y1, op.z1, "drawer sweep")),
           ("base", lay.boost_pocket),
           ("base", Box(us.x0, us.y0, op.z1, us.x1, us.y1, lay.deck_z - t, "USB-C cable drop")),
           ("base", Box(ch.x0, ch.y0, lay.deck_z, ch.x1, ch.y1, hz, "hinge channel"))]
    out += [("base", b) for b in lay.board_keepouts.values()]
    r = P.FOOT_D / 2
    out += [("base", Box(x - r, y - r, -P.FOOT_H, x + r, y + r, 0.0, "foot"))
            for x, y in P.feet(lay)]
    out.append(("base", Box(*P._bb(H.hinge_base_knuckles(lay).val()), "hinge-base")))
    out.append(("lid", Box(*P._bb(H.hinge_lid_knuckles(lay).val()), "hinge-lid")))
    out.append(("lid", lay.lid_pocket))
    for c in lay.lid_catch:
        out += [("base", lay.catch_base_block(c)), ("lid", catch_lid_block_box(lay, c, t))]
    x0, y0, x1, y1 = I.lid_opening(lay)
    out.append(("lid", Box(x0, y0, 0.0, x1, y1, INSERT_MATERIAL, "bezel")))
    return out


def laser_printed(lay: Layout, t: float) -> dict[str, cq.Shape]:
    """One of each laser-only printed fitting, where its first instance goes."""
    out: dict[str, cq.Shape] = {}
    for part, _inst, _frame, s in placed(lay, t):
        out.setdefault(part, s)
    return out


_NOTES = {
    "nut-block-base-leaf": "Glue behind the base back wall at a hinge leaf screw (through the "
                           "deck's notch); M3 square nut in the side pocket.",
    "nut-block-lid-leaf": "Glue behind the lid hinge wall at a hinge leaf screw, up to the lid "
                          "back; M3 square nut in the side pocket.",
    "nut-block-bezel": "Glue in a screwed corner of the lid's opening, from the bezel's back to "
                       "the lid back; M3 square nut in the side pocket.",
    "nut-block-clip": "Glue on the band face in the corner of the lid's left wall and the band "
                      "wall; M3 square nut for the bezel clip's screw.",
    "nut-cup-mt2": "Glue under the deck at MT2, nut pocket against the deck.",
    "standoff-mt2": "Glue on the deck's engraved MT2 outline; the board's M3 screw goes "
                    "through it into the nut cup.",
    "deck-support": "Glue on the deck's engraved support outlines.",
    "mt1-boss": "Glue on the deck's engraved MT1 outline; the loose pin goes in the fitted "
                "revision's hole.",
    "catch-block-base": "Lid catch: glue inside the base's front panel under its top edge, "
                        "hole up; press a 6 x 3 mm disc magnet into it (the lid's attracts: "
                        "check polarity).",
    "catch-block-lid": "Lid catch: glue behind the lid's band face, over the base's block, "
                       "centred on the face's magnet hole; press a 6 x 3 mm disc magnet into the "
                       "hole from the screen side (facing the base's: check polarity).",
    "magnet-block": "Press a 6 x 3 mm disc magnet into the hole (check polarity: the two attract); "
                    "glue one in the drawer's front corner, hole up, and one upside down over "
                    "it in the base's front corner.",
}


def printed_parts(lay: Layout, t: float) -> dict[str, PB.Printed]:
    """The laser route's printed parts: its fittings and the shared parts at
    ``lay``, each bed-checked (``PB.check_bed``)."""
    counts: dict[str, int] = {}
    for part, *_ in placed(lay, t):
        counts[part] = counts.get(part, 0) + 1
    parts: dict[str, PB.Printed] = {}
    for part, s in laser_printed(lay, t).items():
        parts[part] = PB.Printed(s, PB.FLAT, f"{_NOTES[part]} Print {counts[part]}, flat, no "
                                 "supports.")
    parts["hinge-base"] = PB.Printed(H.hinge_base_knuckles(lay).val(), PB.PRINT_POSE["hinge-base"],
                                     "Hinge, base half. Leaf screws M3 x 12 into the nut blocks.")
    parts["hinge-lid"] = PB.Printed(H.hinge_lid_knuckles(lay).val(), PB.PRINT_POSE["hinge-lid"],
                                    "Hinge, lid half. Leaf screws M3 x 12 into the nut blocks.")
    for k, m in MONITORS.items():
        parts[f"bezel-{k}"] = PB.Printed(I.monitor_bezel(m, lay).val(), PB.FLAT,
                                         f"Bezel for {m.title}: print flat.")
        parts[f"retainer-{k}"] = PB.Printed(I.monitor_retainer(m, lay).val(), PB.FLIP,
                                            f"Retainer for {m.title}: print back plate down.")
    for k, b in BATTERIES.items():
        parts[f"packing-{k}"] = PB.Printed(battery_packing(b, lay).val(), PB.FLAT,
                                           f"Packing for {b.title}: print flat.")
    (cx, cy), = P.clip_screws(lay, t)
    parts["bezel-clip"] = PB.Printed(PB.bezel_clip(lay, cx, cy), PB.FLAT,
                                     "Bezel clip: print flat; fit after the bezel.")
    parts["mt1-pin"] = PB.Printed(locating_pin(lay).val(), PB.FLAT,
                                  "MT1 locating pin: print standing; print spares.")
    for name, p in parts.items():
        PB.check_bed(name, PB.posed(p), PRINT_BED)
    return dict(sorted(parts.items()))


def _screw_len(before: float) -> int:
    """Stock M3 screw through ``before`` mm of parts into a nut block."""
    return m3.stock_length(before + NUT_DEPTH1 + m3.THREAD_PAST)


def hardware(lay: Layout, t: float) -> dict[str, int]:
    """Bought hardware for the laser route (name -> count)."""
    body = P.build(lay, t, P.KERF)
    blocks = _blocks(lay, t)
    hw: dict[str, int] = {}

    def add(k, n):
        hw[k] = hw.get(k, 0) + n

    add(f"M3 x {J.TSLOT_SCREW} pan-head screw (T-slot)", len(body.screws))
    add("M3 square nut", len(body.screws) + len(blocks))
    add(f"M3 x {_screw_len(H.LEAF_T + t)} pan-head screw (hinge leaf)",
        len(H.base_leaf_screws(lay)) + len(H.lid_leaf_screws(lay)))
    add(f"M3 x {_screw_len(INSERT_MATERIAL)} pan-head screw (bezel)", len(I.bezel_screws(lay)))
    add(f"M3 x {_screw_len(PB.CLIP_T + t)} pan-head screw (bezel clip)",
        len(P.clip_screws(lay, t)))
    from demobox.parts.board import board_spec
    pcb = board_spec("v3.2").outline.thickness
    c = lay.standoffs[0]
    add(f"M3 x {_screw_len(pcb + (c.z1 - c.z0) + t)} pan-head screw (board, MT2)", 1)
    add(f"M3 x {H.hinge_bolt_length(lay)} bolt (hinge)", len(H.hinge_groups(lay)))
    add("M3 nyloc nut (hinge)", len(H.hinge_groups(lay)))
    add(f"{MAGNET_D:g} x {MAGNET_T:g} mm disc magnet", len(_magnets(lay, t)) + len(_catch(lay, t)))
    add(f"{P.FOOT_D:g} x {P.FOOT_H:g} mm self-adhesive rubber foot", len(P.feet(lay)))
    bp = lay.boost_pocket
    add(f"hook-and-loop tape, {math.floor(bp.size[0] - 10):g} x "
        f"{math.floor(bp.size[1] - 5):g} mm pair (boost converter)", 1)
    return dict(sorted(hw.items()))


# --- assembly ----------------------------------------------------------------------------

def assembly(angle_deg: float, drawer_out: float, monitor: str = PB.ASSEMBLY_MONITOR,
             bank: str = PB.ASSEMBLY_BANK, board: str = PB.ASSEMBLY_BOARD):
    """The laser box in the base frame, as ``printed.body.assembly``: lid
    ``angle_deg`` open, drawer out ``drawer_out``; T-slot nuts and screw
    heads, the bezel and clip screw heads and the magnets as ``hw:`` parts."""
    lay = layout(ROUTES["laser"])
    t = lay.wall
    body = P.build(lay, t, P.KERF)
    m, b = MONITORS[monitor], BATTERIES[bank]
    loc = lay.lid_location(angle_deg)
    shift = cq.Vector(*(v * drawer_out for v in lay.drawer_out))
    items: dict[str, list] = {"base": [], "drawer": [], "lid": []}
    for n, pn in body.panels.items():
        items[pn.frame].append((n, pn.solid(), COLOURS["panel"]))
    for _part, inst, frame, s in body.placed:
        items[frame].append((inst, s, COLOURS["fitting"]))
    for i, s in enumerate(body.screws):
        items[s.frame].append((f"hw:nut-{s.frame}-{i + 1}", _box(s.nut), PB.COLOURS["hw"]))
        items[s.frame].append((f"hw:head-{s.frame}-{i + 1}", _box(s.head), PB.COLOURS["hw"]))
    for inst, (frame, _b, mg, _f) in _magnets(lay, t).items():
        items[frame].append((f"hw:magnet-{frame}", _cyl(mg, (0, 0, 1), P.MAGNET_D / 2,
                                                         P.MAGNET_T), COLOURS["magnet"]))
    for inst, (_part, frame, _s, mg) in _catch(lay, t).items():
        items[frame].append((f"hw:catch-magnet-{inst.removeprefix('catch-block-')}",
                             _cyl((mg.cx, mg.cy, mg.z0), (0, 0, 1), MAGNET_D / 2, MAGNET_T),
                             COLOURS["magnet"]))
    for i, (x, y) in enumerate(P.feet(lay)):
        items["base"].append((f"hw:foot-{i + 1}", _cyl((x, y, -P.FOOT_H), (0, 0, 1),
                                                       P.FOOT_D / 2, P.FOOT_H), (0.1, 0.1, 0.1)))
    peg = lay.pegs[board]
    pin = locating_pin(lay).val().translate(cq.Vector(peg.cx, peg.cy, lay.mt1_boss.z0))
    items["base"] += [("hinge-base", H.hinge_base_knuckles(lay).val(), PB.COLOURS["hinge-base"]),
                      ("mt1-pin", pin, PB.COLOURS["mt1-pin"]),
                      ("board", PB._board_pcb(lay, board), PB.COLOURS["board"])]
    bay = lay.bay
    L_, W_, H_ = b.size
    cy = (bay.y0 + bay.y1) / 2
    items["drawer"] += [("packing", battery_packing(b, lay).val(), PB.COLOURS["packing"]),
                        ("bank", _box(Box(bay.x0, cy - W_ / 2, bay.z0, bay.x0 + L_, cy + W_ / 2,
                                          bay.z0 + H_)), PB.COLOURS["bank"])]
    lid = items["lid"]
    lid += [("hinge-lid", H.hinge_lid_knuckles(lay).val(), PB.COLOURS["hinge-lid"]),
            ("bezel", I.monitor_bezel(m, lay).val(), PB.COLOURS["bezel"]),
            ("retainer", I.monitor_retainer(m, lay).val(), PB.COLOURS["retainer"]),
            ("panel", _box(panel_in_lid(m, lay)), PB.COLOURS["panel"])]
    env = I.driver_envelope(m, lay)
    if env is not None:
        lid.append(("monitor-driver", _box(env), PB.COLOURS["monitor-driver"]))
    for i, (x, y) in enumerate(P.clip_screws(lay, t)):
        lid.append((f"bezel-clip-{i + 1}" if i else "bezel-clip", PB.bezel_clip(lay, x, y),
                    PB.COLOURS["bezel-clip"]))
        lid.append((f"hw:clip-screw-head-{i + 1}", PB._screw_head(x, y, -PB.CLIP_T),
                    PB.COLOURS["hw"]))
    lid += [(f"hw:bezel-screw-head-{i + 1}", PB._screw_head(x, y, 0.0), PB.COLOURS["hw"])
            for i, (x, y) in enumerate(I.bezel_screws(lay))]
    out = list(items["base"])
    out += [(n, s.translate(shift), c) for n, s, c in items["drawer"]]
    out += [(n, s.moved(loc), c) for n, s, c in lid]
    return out
