#!/usr/bin/env python3
"""Write the Blender scenes: per-part STL files and one JSON manifest per render.

``make renders`` runs this, then ``render/render_scene.py`` inside Blender on
each manifest.  The renders (``RENDERS``) are the two routes' assemblies in
four views (``VIEWS``: shut, open from the front, open from behind, and open
with the bank lifted out) and the laser route's panels laid flat as a cut
kit::

    tmp/scene/<route>-<view>.json      tmp/scene/laser-flatpack.json
    tmp/scene/<route>/<part>.stl       tmp/scene/flatpack/<panel>.stl
    tmp/scene/<route>/pigtail-<angle>deg/<leg>.stl
    tmp/scene/test-pattern.png

Parts
-----
Every solid of ``body.assembly(route, 0, False)`` (the box shut, the bank in
its bay) is written once, in its frame's shut placement; a manifest gives
each part a 4 x 4 ``transform`` (row major, mm) for its frame: identity for
the base, the lid's turn (``Layout.lid_location``), or the bank's lift
(``bank_lift``: ``assembly(..., bank_out=True)``'s BANK_OUT_LIFT clear of the
rim).  Which frame a part is in is read off the assembly itself: a part that
moves when the lid opens is in the lid frame, one that moves when the bank
comes out is in the bank frame.  ``test_scene`` checks every part lands where
the assembly puts it in every view.

The assembly's bought parts are plain blocks; the renders keep the board's
PCB, the monitor (taped at ``monitor_space``), the boost module (taped in the
lid strip, R25) and the bank as they are, and add representative solids from
the part data so a visitor sees a recognisable thing (``bought_parts``):

* the board's Pmod sockets, USB-C shell, 7-segment display, DIP switch and
  LEDs, from the submodule's ``BoardSpec`` features (heights are render-only
  guesses, ``COMPONENT_H``);
* in place of the assembly's ``tinyvga`` block (``DETAIL``): the TinyVGA PCB
  and DE-15 socket (``demobox.parts.tinyvga``) in J13, and the 90 degree VGA
  adapter on the DE-15 (R16a), together filling the block, and the TinyVGA's
  header in J13's socket;
* in place of the ``vga-plug`` block (the plug and its stiff run): the
  monitor's moulded plug in the adapter's socket (``vga-plug-hood``), and the
  monitor's pigtail (``pigtail``) drawn along ``checks.pigtail_path`` at the
  view's lid angle (R4): from the panel's cable edge, along the lid strip,
  through the hinge notch, down and along the stiff run in the bank row's
  +X back corner into the hood;
* the right-angle USB-C plug in J1 (``board_keepouts[.../usb_plug]``) and
  the bank's cable to it along ``checks.usb_path``.  The design bank's cable
  is built in, so both are in the bank frame: in the bank-out view they come
  up with the bank, unplugged;
* the monitor's screen: an emissive quad over the active area
  (``Monitor.active``/``active_offset``) on the taped panel's face, carrying
  ``test_pattern()``.

The boost module's leads are not drawn.

Dimensions
----------
Each manifest's ``dimensions`` (``view_dimensions``) are the layout's sizes
for that view, in the world frame and units of the parts (mm), labelled
through ``geom.mm`` like the sheets.  ``render_scene.py`` frames them and
writes their pixel positions to ``<png>.dims.json`` for the overlay.

The scene uses Tim's monitor (``taobao-tim``), the Xiaomi PB2020 bank and the
v3.3 board: ``body.ASSEMBLY_MONITOR``/``ASSEMBLY_BANK``/``ASSEMBLY_BOARD``.

Colours (render palette, ``PALETTE``): plywood light birch; the printed
route's base and lid a neutral PLA grey; the laser route's printed fittings
(knuckle blocks, seal bead, magnet blocks) and the loose MT1 pin a distinct
PLA blue; the ETR board's PCB purple; the monitor body black; the bank light
grey; the boost module blue shrink-wrap; magnets nickel; rods steel.

Run: make renders (or ``python scripts/export_scene.py [--out DIR] [names]``)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import cadquery as cq  # noqa: E402

import demobox  # noqa: E402,F401  (puts the submodule on sys.path)
from demobox.checks import pigtail_path, usb_cable, usb_path  # noqa: E402
from demobox.geom import Box, mm  # noqa: E402
from demobox.layout import LID_OPEN_DEG, ROUTES, Layout, layout, tinyvga_offset  # noqa: E402
from demobox.parts.board import board_spec  # noqa: E402
from demobox.parts.cables import CABLES  # noqa: E402
from demobox.parts.monitors import MONITORS  # noqa: E402
from demobox.parts.tinyvga import TINYVGA  # noqa: E402
from demobox.printed import body  # noqa: E402
from demobox.shared.solids import BANK_OUT_LIFT, monitor_block  # noqa: E402

OUT = ROOT / "tmp" / "scene"

#: STL chord (mm) and angular (rad) tolerance: coarser than the print STLs.
STL_TOLERANCE = 0.1
STL_ANGULAR = 0.15

RESOLUTION = (1600, 1200)
SAMPLES = 256
LENS_MM = 35.0


@dataclass(frozen=True)
class View:
    lid_deg: float
    bank_out: bool        # the bank lifted out of its bay (BANK_OUT_LIFT above the rim)
    azimuth_deg: float    # camera bearing about Z: 0 in front (-Y), +90 at the right (+X)
    elevation_deg: float  # camera above the horizon


VIEWS: dict[str, View] = {
    "closed": View(0.0, False, -35.0, 28.0),
    "open-front": View(LID_OPEN_DEG, False, 28.0, 34.0),
    "open-back": View(LID_OPEN_DEG, False, 240.0, 22.0),
    "bank-out": View(LID_OPEN_DEG, True, -40.0, 30.0),
}
#: The flat-pack: looking down on the kit from the front, steeply.
FLATPACK_VIEW = (0.0, 62.0)
FLATPACK_GAP = 12.0

RENDERS: tuple[str, ...] = tuple(f"{r}-{v}" for r in ROUTES for v in VIEWS) + ("laser-flatpack",)

#: Material finishes ``render_scene.py`` knows; the manifest's ``colour`` is
#: the base colour.
MATERIALS = ("plywood", "pla", "metal", "rubber", "plastic", "pcb")

PALETTE: dict[str, tuple[float, float, float]] = {
    "plywood": (0.80, 0.65, 0.45),
    "pla": (0.33, 0.34, 0.35),
    "pla-shared": (0.12, 0.42, 0.72),
    "metal": (0.30, 0.30, 0.32),
    "steel": (0.62, 0.62, 0.64),
    "nickel": (0.70, 0.70, 0.72),
    "rubber": (0.03, 0.03, 0.03),
    "black": (0.015, 0.015, 0.018),
    "moulded": (0.03, 0.03, 0.035),
    "bank": (0.78, 0.78, 0.76),
    "boost": (0.08, 0.20, 0.50),
    "pcb-purple": (0.30, 0.08, 0.45),
    "pcb-tinyvga": (0.02, 0.12, 0.05),
    "vga-blue": (0.05, 0.15, 0.55),
    "silver": (0.75, 0.75, 0.77),
    "switch-red": (0.70, 0.05, 0.05),
    "display": (0.12, 0.12, 0.12),
    "led": (0.95, 0.85, 0.75),
}

#: Printed parts in the distinct PLA blue: the laser route's printed fittings
#: (among the plywood) and the loose MT1 pin.
BLUE_PRINTED = ("knuckles-", "seal-bead", "magnet-block", "mt1-pin")

#: Render-only component heights above the PCB top (mm): not in the board data,
#: so guesses good enough to read as the part.  They are not used for any fit.
COMPONENT_H = {"pmod": 5.5, "usb_power": 3.2, "display7": 6.5, "switch": 4.0, "led": 0.8}

#: The assembly's plain blocks the scene draws in detail instead: block ->
#: the parts (``bought_parts``) standing in for it.  The ``vga-plug`` block
#: also holds the pigtail's stiff run, drawn with the pigtail.  (The
#: TinyVGA's header, ``tinyvga-header``, is in J13's socket, outside the
#: block.)
DETAIL: dict[str, tuple[str, ...]] = {
    "tinyvga": ("tinyvga-pcb", "tinyvga-de15", "vga-adapter"),
    "vga-plug": ("vga-plug-hood",),
}

PIGTAIL_R = CABLES["monitor-pigtail"].dia / 2

#: The screen quad stands this far proud of the monitor's face (no z-fight).
SCREEN_PROUD = 0.05

PATTERN_SIZE = (1024, 600)   # the 7" panel's native resolution


# --- transforms ---------------------------------------------------------------------

IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _loc_matrix(loc: cq.Location) -> list[float]:
    t = loc.wrapped.Transformation()
    m = [t.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4)] + [0.0, 0.0, 0.0, 1.0]
    return [0.0 if abs(v) < 1e-12 else v for v in m]


def bank_lift(lay: Layout) -> float:
    """How far ``assembly(..., bank_out=True)`` lifts the bank: off the bay
    floor to BANK_OUT_LIFT above the rim."""
    return lay.rim_z + BANK_OUT_LIFT - lay.bank_bay.z0


def frame_matrix(lay: Layout, frame: str, lid_deg: float, bank_out: bool) -> list[float]:
    """Row-major 4 x 4 moving ``frame``'s solids from their shut placement in
    the base frame (as ``body.assembly(route, 0, False)`` gives them): the
    lid turned ``lid_deg`` open about the hinge axis (``lid_location(lid_deg)``
    after undoing ``lid_location(0)``), the bank lifted ``bank_lift`` when
    ``bank_out``."""
    if frame == "base":
        return list(IDENTITY)
    if frame == "bank":
        m = list(IDENTITY)
        m[11] = bank_lift(lay) if bank_out else 0.0
        return m
    if frame == "lid":
        return _loc_matrix(lay.lid_location(lid_deg) * lay.lid_location(0.0).inverse)
    raise ValueError(f"unknown frame {frame!r}")


# --- test pattern -------------------------------------------------------------------

def test_pattern(path: Path) -> Path:
    """A TT VGA-style test pattern: SMPTE-ish colour bars, a grey ramp and a
    checker strip, with a caption.  PATTERN_SIZE pixels."""
    from PIL import Image, ImageDraw, ImageFont
    w, h = PATTERN_SIZE
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    bars = [(192, 192, 192), (192, 192, 0), (0, 192, 192), (0, 192, 0),
            (192, 0, 192), (192, 0, 0), (0, 0, 192)]
    top = int(h * 0.62)
    bw = w / len(bars)
    for i, c in enumerate(bars):
        d.rectangle([round(i * bw), 0, round((i + 1) * bw) - 1, top], fill=c)
    mid = int(h * 0.72)
    for i, c in enumerate(reversed(bars)):
        d.rectangle([round(i * bw), top, round((i + 1) * bw) - 1, mid],
                    fill=c if i % 2 == 0 else (16, 16, 16))
    for x in range(w):                                     # grey ramp
        g = round(255 * x / (w - 1))
        d.line([x, mid, x, int(h * 0.84)], fill=(g, g, g))
    sq = 20
    for x in range(0, w, sq):                              # checker strip
        for y in range(int(h * 0.84), h, sq):
            if (x // sq + y // sq) % 2 == 0:
                d.rectangle([x, y, x + sq - 1, y + sq - 1], fill=(235, 235, 235))
    try:
        font = ImageFont.load_default(size=56)
    except TypeError:                                      # Pillow < 10.1
        font = ImageFont.load_default()
    text = "TINY TAPEOUT  VGA"
    tb = d.textbbox((0, 0), text, font=font)
    tx, ty = (w - (tb[2] - tb[0])) // 2, int(h * 0.31) - (tb[3] - tb[1]) // 2
    d.rectangle([tx - 24, ty - 18, tx + tb[2] - tb[0] + 24, ty + tb[3] - tb[1] + 30],
                fill=(10, 10, 10))
    d.text((tx - tb[0], ty - tb[1]), text, font=font, fill=(255, 255, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    im.save(path)
    return path


# --- bought parts ------------------------------------------------------------------

def _box(b: Box) -> cq.Solid:
    return cq.Solid.makeBox(*b.size, cq.Vector(b.x0, b.y0, b.z0))


def _to_base(lay: Layout, x0, y0, z0, x1, y1, z1) -> Box:
    """A board-frame box in the base frame (``demobox.layout``: the board
    turned +90 degrees about Z, ``base = (ox - by, oy + bx, oz + bz)``)."""
    ox, oy, oz = lay.board_origin
    return Box(ox - y1, oy + x0, oz + z0, ox - y0, oy + x1, oz + z1)


def _tube(pts, r: float) -> list[cq.Shape]:
    """A cable along the polyline ``pts``: a cylinder of radius ``r`` per
    leg, with a sphere at each end so consecutive legs join without a gap
    at the corner."""
    out = []
    for a, b in zip(pts, pts[1:]):
        if math.dist(a, b) < 1e-9:
            continue
        va, vb = cq.Vector(*a), cq.Vector(*b)
        leg = cq.Solid.makeCylinder(r, (vb - va).Length, va, vb - va)
        for v in (va, vb):
            leg = leg.fuse(cq.Solid.makeSphere(r, v, angleDegrees1=-90, angleDegrees2=90))
        out.append(leg)
    return out


def pigtail_points(lay: Layout, angle_deg: float,
                   board: str = body.ASSEMBLY_BOARD) -> list[tuple[float, float, float]]:
    """The pigtail's cable (R4): ``checks.pigtail_path`` at ``angle_deg``
    (base frame) up to the back of the plug body; its last leg, the plug
    body to its face in the adapter, is the hood (``tinyvga_boxes``)."""
    return pigtail_path(lay, angle_deg, board)[:-1]


def pigtail(lay: Layout, angle_deg: float, board: str = body.ASSEMBLY_BOARD):
    """``(name, solid, frame)`` per leg of the pigtail at ``angle_deg``: in
    the base frame, already where the lid at that angle puts it."""
    legs = _tube(pigtail_points(lay, angle_deg, board), PIGTAIL_R)
    return [(f"pigtail-{i}", s, "base") for i, s in enumerate(legs)]


def tinyvga_boxes(lay: Layout, board: str = body.ASSEMBLY_BOARD) -> dict[str, Box]:
    """The TinyVGA's blocks in the base frame: ``pcb``, ``header``, ``de15``,
    the 90 degree ``adapter`` on the DE-15 (R16a: ``CABLES["vga-90-adapter"]
    .plug`` = 35 along the D-sub's long axis, 17 out of the DE-15 face, 20
    tall, centred on the socket and the plug's axis; the PCB, DE-15 and
    adapter together are the layout's ``<board>/tinyvga``, the header is in
    J13's socket) and the monitor's moulded plug ``hood`` in
    the adapter's socket: the first PLUG_BODY_LEN of ``<board>/vga_plug``."""
    dx, dy, dz = tinyvga_offset(board)

    def tv(b: Box) -> Box:
        m = b.moved(dx, dy, dz)
        return _to_base(lay, m.x0, m.y0, m.z0, m.x1, m.y1, m.z1)

    span, out, tall = CABLES["vga-90-adapter"].plug
    d = TINYVGA.de15
    cx, zc = (d.x0 + d.x1) / 2, (TINYVGA.plug_z0 + TINYVGA.plug_z1) / 2
    adapter = Box(cx - span / 2, d.y0 - out, zc - tall / 2, cx + span / 2, d.y0, zc + tall / 2)
    plug = lay.board_keepouts[f"{board}/vga_plug"]
    return {"pcb": tv(TINYVGA.pcb), "header": tv(TINYVGA.header), "de15": tv(TINYVGA.de15),
            "adapter": tv(adapter), "hood": replace(plug, y1=plug.y0 + TINYVGA.plug_body_len)}


def bought_parts(lay: Layout, board: str = body.ASSEMBLY_BOARD):
    """Representative solids the assembly leaves out or draws as plain blocks,
    in the base frame (lid shut, bank in): ``(name, solid, material, colour,
    frame)``.  The pigtail, which depends on the lid angle, is ``pigtail``."""
    spec = board_spec(board)
    top = spec.outline.thickness
    out = []

    def add(name, solid, material, colour, frame="base"):
        out.append((name, solid, material, PALETTE[colour], frame))

    for p in spec.pmods:
        add(f"pmod-{p.designator}", _box(_to_base(lay, p.body_x0, p.body_y0, top, p.body_x1,
                                                  p.body_y1, top + COMPONENT_H["pmod"])),
            "plastic", "black")
    for f in spec.features:
        if f.kind == "usb_power":
            add("usb-c-shell", _box(_to_base(lay, f.x0, f.y0, top, f.x1, f.y1,
                                             top + COMPONENT_H["usb_power"])), "metal", "silver")
        elif f.kind == "display7":
            add("display-7seg", _box(_to_base(lay, f.x0, f.y0, top, f.x1, f.y1,
                                              top + COMPONENT_H["display7"])),
                "plastic", "display")
        elif f.kind == "switch":
            add("dip-switch", _box(_to_base(lay, f.x0, f.y0, top, f.x1, f.y1,
                                            top + COMPONENT_H["switch"])), "plastic", "switch-red")
        elif f.kind == "led":
            add(f"led-{f.designator}", _box(_to_base(lay, f.x0, f.y0, top, f.x1, f.y1,
                                                     top + COMPONENT_H["led"])), "plastic", "led")

    # the TinyVGA in J13 (pmod3), its adapter and the monitor's plug in it
    tvb = tinyvga_boxes(lay, board)
    add("tinyvga-pcb", _box(tvb["pcb"]), "pcb", "pcb-tinyvga")
    add("tinyvga-header", _box(tvb["header"]), "plastic", "black")
    add("tinyvga-de15", _box(tvb["de15"]), "plastic", "vga-blue")
    add("vga-adapter", _box(tvb["adapter"]), "plastic", "moulded")
    add("vga-plug-hood", _box(tvb["hood"]), "plastic", "moulded")

    # the right-angle USB-C plug in J1 and the bank's built-in cable to it:
    # they come out with the bank
    add("usb-c-plug", _box(lay.board_keepouts[f"{board}/usb_plug"]), "plastic", "moulded",
        "bank")
    for i, s in enumerate(_tube(usb_path(lay, board)[:-1], usb_cable(lay).dia / 2)):
        add(f"usb-c-cable-{i}", s, "rubber", "black", "bank")
    return out


def screen_quad(lay: Layout):
    """The monitor's active area with the lid shut, in the base frame (the
    lid frame + the hinge axis), like the part STLs: four corners (mm), image
    lower-left, lower-right, upper-right, upper-left, SCREEN_PROUD under the
    taped panel's face (``monitor_block``; screen down, its cable edge -- the
    image's bottom -- towards the hinge: panel u -> +x, v -> -y)."""
    m = MONITORS[lay.monitor]
    pb = monitor_block(lay).BoundingBox()
    (aw, ah), (au, av) = m.active, m.active_offset
    hy, hz = lay.hinge_axis
    z = hz + pb.zmin - SCREEN_PROUD
    x0, x1 = pb.xmin + au, pb.xmin + au + aw
    y_lo, y_hi = hy + pb.ymax - av, hy + pb.ymax - av - ah        # image bottom, image top
    return [[x0, y_lo, z], [x1, y_lo, z], [x1, y_hi, z], [x0, y_hi, z]]


# --- route scenes ------------------------------------------------------------------

def _bbox(s: cq.Shape) -> tuple[float, ...]:
    b = s.BoundingBox()
    return b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax


def _same(a, b) -> bool:
    return all(abs(p - q) < 1e-6 for p, q in zip(a, b))


def _material(name: str, laser_panels) -> tuple[str, tuple[float, float, float]]:
    if name.startswith("hw:catch-magnet"):
        return "metal", PALETTE["nickel"]
    if name.startswith("hw:"):                              # the hinge rod, board pins
        return "metal", PALETTE["steel"]
    if name == "board":
        return "pcb", PALETTE["pcb-purple"]
    if name == "monitor":
        return "plastic", PALETTE["black"]
    if name == "boost":
        return "plastic", PALETTE["boost"]
    if name == "bank":
        return "plastic", PALETTE["bank"]
    if name in laser_panels:
        return "plywood", PALETTE["plywood"]
    if name.startswith(BLUE_PRINTED):
        return "pla", PALETTE["pla-shared"]
    return "pla", PALETTE["pla"]


def scene_parts(route: str, board: str = body.ASSEMBLY_BOARD):
    """``route``'s parts, shut, in the base frame: ``(name, solid, frame,
    material, colour)``: the assembly's solids (less the ``DETAIL`` blocks),
    each in the frame it moves with, then ``bought_parts``."""
    lay = layout(ROUTES[route])
    shut = body.assembly(route, 0.0, False, board=board)
    names = [n for n, _, _ in shut]
    if len(set(names)) != len(names):
        raise ValueError(f"{route}: assembly part names are not unique")
    lid_moved = {n: _bbox(s) for n, s, _ in body.assembly(route, LID_OPEN_DEG, False, board=board)}
    bank_moved = {n: _bbox(s) for n, s, _ in body.assembly(route, 0.0, True, board=board)}
    laser_panels = set()
    if route == "laser":
        from demobox.laser import panels as P
        laser_panels = set(P.build(lay, lay.wall, P.KERF).panels)
    parts = []
    for name, shape, _colour in shut:
        if name in DETAIL:
            continue
        bb = _bbox(shape)
        frame = ("lid" if not _same(bb, lid_moved[name]) else
                 "bank" if not _same(bb, bank_moved[name]) else "base")
        parts.append((name, shape, frame, *_material(name, laser_panels)))
    parts += [(n, s, frame, mat, c) for n, s, mat, c, frame in bought_parts(lay, board)]
    return parts


def _write_stl(shape: cq.Shape, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(cq.Workplane("XY").add(shape), str(path), "STL",
                        tolerance=STL_TOLERANCE, angularTolerance=STL_ANGULAR)


def _entry(name: str, shape: cq.Shape, rel: Path, frame: str, material: str, colour,
           out: Path) -> dict:
    _write_stl(shape, out / rel)
    return {"part": name, "file": str(rel), "frame": frame, "material": material,
            "colour": list(colour)}


def route_parts(route: str, out: Path) -> list[dict]:
    """Write ``route``'s part STLs under ``out/<route>/``; return each part's
    ``{part, file, frame, material, colour}``."""
    return [_entry(name, shape, Path(route) / f"{name.replace(':', '_')}.stl", frame,
                   material, colour, out)
            for name, shape, frame, material, colour in scene_parts(route)]


def pigtail_parts(route: str, angle_deg: float, out: Path) -> list[dict]:
    """Write the pigtail's legs at ``angle_deg`` under
    ``out/<route>/pigtail-<angle>deg/``; return their entries."""
    lay = layout(ROUTES[route])
    d = Path(route) / f"pigtail-{angle_deg:g}deg"
    return [_entry(name, s, d / f"{name}.stl", frame, "rubber", PALETTE["black"], out)
            for name, s, frame in pigtail(lay, angle_deg)]


# --- dimensions --------------------------------------------------------------------

#: How far a dimension line stands out from its anchors (mm, outward).
DIM_OFFSET = 15.0
#: The lid-angle arc's radius about the hinge axis (mm).
DIM_ARC_R = 40.0


def _apply(m: list[float], p) -> list[float]:
    return [sum(m[4 * r + c] * v for c, v in enumerate((*p, 1.0))) for r in range(3)]


def _linear(value: float, a, b, offset, fallback: bool = False) -> dict:
    """A linear dimension from ``a`` to ``b`` (world, mm), its line ``offset``
    out from them, labelled ``geom.mm(value)``: the layout's number.  Raises
    if the anchors do not span that number (the label would lie)."""
    label = mm(value)
    span = math.dist(a, b)
    if mm(span) != label:
        raise ValueError(f"dimension {label}: its anchors span {mm(span)}")
    return {"label": label, "kind": "linear", "a": [float(v) for v in a],
            "b": [float(v) for v in b], "offset": [float(v) for v in offset],
            "fallback": fallback}


def _open_lid_corners(lay: Layout, lid_deg: float) -> list[list[float]]:
    """The lid's outer box corners (``lid_outer``, shut, in the base frame),
    moved by the lid frame's transform at ``lid_deg``: where the parts' lid
    transform puts them."""
    o, (hy, hz) = lay.lid_outer, lay.hinge_axis
    m = frame_matrix(lay, "lid", lid_deg, False)
    return [_apply(m, (x, hy + y, hz + z)) for x in (o.x0, o.x1) for y in (o.y0, o.y1)
            for z in (o.z0, o.z1)]


def flatpack_placement(lay: Layout) -> dict[str, tuple[float, float, float, float, float]]:
    """The laser panels laid flat, shelf-packed in rows with FLATPACK_GAP
    between them: panel -> (x, y, w, h, t), its (u, v) bounds' corner at
    (x, y) on the ground, in packing order."""
    from demobox.laser import panels as P
    pans = P.build(lay, lay.wall, P.KERF).panels
    size = {}
    for name, pn in pans.items():
        u0, v0, u1, v1 = pn.shape.bounds
        size[name] = (u1 - u0, v1 - v0, pn.t)
    area = sum((w + FLATPACK_GAP) * (h + FLATPACK_GAP) for w, h, _ in size.values())
    row_w = max(max(w for w, _, _ in size.values()), math.sqrt(area * 4 / 3) * 1.05)
    order = sorted(size, key=lambda n: (-size[n][1], -size[n][0], n))
    x = y = row_h = 0.0
    out = {}
    for name in order:
        w, h, t = size[name]
        if x > 0 and x + w > row_w:
            x, y, row_h = 0.0, y + row_h + FLATPACK_GAP, 0.0
        out[name] = (x, y, w, h, t)
        x += w + FLATPACK_GAP
        row_h = max(row_h, h)
    return out


def view_dimensions(lay: Layout, route: str, view: str) -> list[dict]:
    """The dimensions drawn on ``route``'s render in ``view`` (a ``VIEWS``
    key, or ``"flatpack"`` for the laser kit), in the manifest's world frame
    and units (mm, like the parts' transforms).

    Each is ``{"label", "kind": "linear", "a", "b", "offset", "fallback"}``
    (anchors ``a``, ``b`` on the model; the line at ``a + offset`` ..
    ``b + offset``, DIM_OFFSET out, away from the model) or ``{"label",
    "kind": "angle", "centre", "a", "b", "fallback"}`` (the arc about
    ``centre`` from arm point ``a`` to ``b``).  Labels are the layout's
    numbers through ``geom.mm`` (the sheets' rounding); the anchors come
    from the layout's boxes moved by ``frame_matrix``, and must span them.

    * closed: W along the front, D along the left side (on the ground), H
      up the front-right edge to the shut lid's top;
    * open-front: W, the open height (ground to the open lid's top, the
      layout's ``lid_profile_yz``) up the right side, and the lid's
      LID_OPEN_DEG arc about the hinge axis at the right face;
    * open-back: D and, chained behind it, the open lid's reach behind the
      back face, both along the left side on the ground;
    * bank-out: the bank bay's length (X) along its front rim edge and its
      width (Y) along its left rim edge;
    * flatpack: each panel's (u, v) size at its place in the kit (W along
      its front edge, H along its left), then two ``fallback`` entries, the
      kit's overall extent in X (2 DIM_OFFSET in front of it) and in Y (2
      DIM_OFFSET left of it) (rulings P2, P2b: drawn only when the
      per-panel labels do not fit).
    """
    off = DIM_OFFSET
    if view == "flatpack":
        if route != "laser":
            raise ValueError(f"the flat-pack is the laser route's, not {route!r}")
        place = flatpack_placement(lay)
        dims = []
        for x, y, w, h, t in place.values():
            dims.append(_linear(w, (x, y, t), (x + w, y, t), (0.0, -off, 0.0)))
            dims.append(_linear(h, (x, y, t), (x, y + h, t), (-off, 0.0, 0.0)))
        x0 = min(x for x, _y, _w, _h, _t in place.values())
        y0 = min(y for _x, y, _w, _h, _t in place.values())
        x1 = max(x + w for x, _y, w, _h, _t in place.values())
        y1 = max(y + h for _x, y, _w, h, _t in place.values())
        dims.append(_linear(x1 - x0, (x0, y0, 0.0), (x1, y0, 0.0), (0.0, -2 * off, 0.0),
                            fallback=True))
        dims.append(_linear(y1 - y0, (x0, y0, 0.0), (x0, y1, 0.0), (-2 * off, 0.0, 0.0),
                            fallback=True))
        return dims
    v = VIEWS[view]
    o, lo, bay = lay.outer, lay.lid_outer, lay.bank_bay
    x0, y0, z0, x1, y1 = o.x0, o.y0, o.z0, o.x1, o.y1
    if view == "closed":
        lid_top = max(p[2] for p in _open_lid_corners(lay, v.lid_deg))
        return [_linear(o.size[0], (x0, y0, z0), (x1, y0, z0), (0.0, -off, 0.0)),
                _linear(o.size[1], (x0, y0, z0), (x0, y1, z0), (-off, 0.0, 0.0)),
                _linear(o.size[2] + lo.size[2], (x1, y0, z0), (x1, y0, lid_top),
                        (off, 0.0, 0.0))]
    _py0, _pz0, back, top = lay.lid_profile_yz(v.lid_deg).bounds
    corners = _open_lid_corners(lay, v.lid_deg)
    if view == "open-front":
        hi = max(corners, key=lambda p: p[2])
        hy, hz = lay.hinge_axis
        m = frame_matrix(lay, "lid", v.lid_deg, False)
        arm = (x1, hy - DIM_ARC_R, hz)                     # along the shut lid, forward
        return [_linear(o.size[0], (x0, y0, z0), (x1, y0, z0), (0.0, -off, 0.0)),
                _linear(top - z0, (x1, hi[1], z0), (x1, hi[1], hi[2]), (off, 0.0, 0.0)),
                {"label": f"{v.lid_deg:g}\N{DEGREE SIGN}", "kind": "angle",
                 "centre": [x1, hy, hz], "a": list(arm), "b": _apply(m, arm),
                 "fallback": False}]
    if view == "open-back":
        far = max(corners, key=lambda p: p[1])
        return [_linear(o.size[1], (x0, y0, z0), (x0, y1, z0), (-off, 0.0, 0.0)),
                _linear(back - y1, (x0, y1, z0), (x0, far[1], z0), (-off, 0.0, 0.0))]
    if view == "bank-out":
        z = bay.z1
        return [_linear(bay.size[0], (bay.x0, bay.y0, z), (bay.x1, bay.y0, z), (0.0, -off, 0.0)),
                _linear(bay.size[1], (bay.x0, bay.y0, z), (bay.x0, bay.y1, z), (-off, 0.0, 0.0))]
    raise ValueError(f"no dimensions for view {view!r}")


def view_manifest(route: str, view: str, entries: list[dict], pig: list[dict],
                  pattern: str) -> dict:
    """The manifest for ``route`` in ``view``: the shut ``entries`` with their
    frames' transforms, the pigtail at the view's angle (``pig``), the
    screen and the view's ``dimensions`` (``view_dimensions``)."""
    lay = layout(ROUTES[route])
    v = VIEWS[view]
    parts = [{**e, "transform": frame_matrix(lay, e["frame"], v.lid_deg, v.bank_out)}
             for e in entries + pig]
    screen = {"part": "screen", "quad": screen_quad(lay), "image": pattern,
              "transform": frame_matrix(lay, "lid", v.lid_deg, v.bank_out)}
    return {"name": f"{route}-{view}", "route": route, "view": view, "lid_deg": v.lid_deg,
            "bank_out": v.bank_out, "monitor": lay.monitor,
            "bank": lay.bank, "board": body.ASSEMBLY_BOARD,
            "camera": {"azimuth_deg": v.azimuth_deg, "elevation_deg": v.elevation_deg,
                       "lens_mm": LENS_MM},
            "resolution": list(RESOLUTION), "samples": SAMPLES,
            "parts": parts, "screens": [screen],
            "dimensions": view_dimensions(lay, route, view)}


# --- flat pack ---------------------------------------------------------------------

def flatpack(out: Path) -> dict:
    """Every laser panel lying flat (its own (u, v) in the XY plane, 3 mm
    thick), where ``flatpack_placement`` packs it, with the kit's
    ``dimensions``."""
    from demobox.laser import panels as P
    lay = layout(ROUTES["laser"])
    pans = P.build(lay, lay.wall, P.KERF).panels
    parts = []
    for name, (x, y, _w, _h, _t) in flatpack_placement(lay).items():
        pn = pans[name]
        u0, v0, _u1, _v1 = pn.shape.bounds
        s = replace(pn, normal="z", z0=0.0).solid().translate(cq.Vector(-u0, -v0, 0.0))
        rel = Path("flatpack") / f"{name}.stl"
        _write_stl(s, out / rel)
        m = list(IDENTITY)
        m[3], m[7] = x, y
        parts.append({"part": name, "file": str(rel), "frame": "flat", "material": "plywood",
                      "colour": list(PALETTE["plywood"]), "transform": m})
    az, el = FLATPACK_VIEW
    return {"name": "laser-flatpack", "route": "laser", "view": "flatpack",
            "camera": {"azimuth_deg": az, "elevation_deg": el, "lens_mm": LENS_MM},
            "resolution": list(RESOLUTION), "samples": SAMPLES, "parts": parts,
            "screens": [], "dimensions": view_dimensions(lay, "laser", "flatpack")}


# --- driver ------------------------------------------------------------------------

def export(out: Path = OUT, names=RENDERS) -> dict[str, Path]:
    """Write the manifests ``names`` (and what they reference) under ``out``;
    return name -> manifest path."""
    unknown = set(names) - set(RENDERS)
    if unknown:
        raise ValueError(f"unknown renders {sorted(unknown)}; renders are {list(RENDERS)}")
    out.mkdir(parents=True, exist_ok=True)
    pattern = test_pattern(out / "test-pattern.png").name
    written = {}

    def write(manifest: dict) -> None:
        p = out / f"{manifest['name']}.json"
        p.write_text(json.dumps(manifest, indent=1) + "\n")
        written[manifest["name"]] = p
        print(f"{p.relative_to(out.parent) if out.parent in p.parents else p}: "
              f"{len(manifest['parts'])} parts")

    for route in ROUTES:
        views = [v for v in VIEWS if f"{route}-{v}" in names]
        if not views:
            continue
        entries = route_parts(route, out)
        pigs = {a: pigtail_parts(route, a, out) for a in {VIEWS[v].lid_deg for v in views}}
        for v in views:
            write(view_manifest(route, v, entries, pigs[VIEWS[v].lid_deg], pattern))
    if "laser-flatpack" in names:
        write(flatpack(out))
    return written


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("names", nargs="*", default=list(RENDERS))
    a = ap.parse_args()
    export(a.out, tuple(a.names))
    return 0


if __name__ == "__main__":
    sys.exit(main())
