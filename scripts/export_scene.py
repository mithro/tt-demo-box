#!/usr/bin/env python3
"""Write the Blender scenes: per-part STL files and one JSON manifest per render.

``make renders`` runs this, then ``render/render_scene.py`` inside Blender on
each manifest.  The renders (``RENDERS``) are the two routes' assemblies in
four views (``VIEWS``) and the laser route's panels laid flat as a cut kit::

    tmp/scene/<route>-<view>.json      tmp/scene/laser-flatpack.json
    tmp/scene/<route>/<part>.stl       tmp/scene/flatpack/<panel>.stl
    tmp/scene/test-pattern.png

Parts
-----
Every solid of ``demobox.printed.body.assembly(route, 0, 0)`` (the box shut)
is written once, in its frame's closed placement; a manifest gives each part
a 4 x 4 ``transform`` (row major, mm) for its frame: identity for the base,
the drawer's slide (``Layout.drawer_out`` x mm), or the lid's turn
(``Layout.lid_location``).  Which frame a part is in is read off the
assembly itself: a part that moves when the lid opens is in the lid frame,
one that moves when the drawer opens is in the drawer frame.

The assembly's bought parts are plain blocks (monitor body, bank, bare PCB);
the renders add representative solids from the part data so a visitor sees a
recognisable thing (``bought_parts``):

* the board's Pmod sockets, USB-C shell, 7-segment display, DIP switch and
  LEDs, from the submodule's ``BoardSpec`` features (heights are render-only
  guesses, ``COMPONENT_H``);
* the TinyVGA PCB, its DE-15 socket and header (``demobox.parts.tinyvga``) in
  J13, the moulded VGA plug and 90 degree adapter filling the layout's plug
  keep-out, and the slim VGA cable rising into the hinge cable channel;
* the right-angle USB-C plug in J1 (``board_keepouts[.../usb_plug]``) and its
  cable dropping through the deck's slot;
* the monitor's screen: an emissive quad over the active area
  (``Monitor.active``/``active_offset``) carrying ``test_pattern()``.

Internal cables (bank to board, the boost lead) are not drawn: they are out
of sight under the deck.  Every ``hw:`` keep-out (screw heads, T-slot nuts,
magnets, feet) is rendered, as dark metal, nickel or black rubber; the laser
route's T-slot screw heads, box keep-outs in the assembly, are drawn as the
round heads inscribed in them (``_round_head``).

The scene uses Tim's monitor (``taobao-tim``), the Xiaomi PB2020 bank and the
v3.2 board: ``body.ASSEMBLY_MONITOR``/``ASSEMBLY_BANK``/``ASSEMBLY_BOARD``.

Colours (render palette, ``PALETTE``): plywood light birch; the route's own
printed parts a neutral PLA grey; the parts both routes share (hinge, bezel,
clip, retainer, packing, MT1 pin) a distinct PLA blue; the ETR board's PCB
purple; the monitor body black.

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
from demobox.checks import _exit_point, panel_in_lid  # noqa: E402
from demobox.geom import Box  # noqa: E402
from demobox.layout import (LID_OPEN_DEG, ROUTES, VGA_PLUG_STRAIGHT, Layout,  # noqa: E402
                            exit_edge, layout, tinyvga_offset)
from demobox.parts.board import board_spec  # noqa: E402
from demobox.parts.cables import CABLES  # noqa: E402
from demobox.parts.monitors import MONITORS  # noqa: E402
from demobox.parts.tinyvga import TINYVGA  # noqa: E402
from demobox.printed import body  # noqa: E402

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
    drawer: bool          # drawer pulled out its full travel
    azimuth_deg: float    # camera bearing about Z: 0 in front (-Y), +90 at the right (+X)
    elevation_deg: float  # camera above the horizon


VIEWS: dict[str, View] = {
    "closed": View(0.0, False, -35.0, 28.0),
    "open-front": View(LID_OPEN_DEG, False, 28.0, 34.0),
    "open-back": View(LID_OPEN_DEG, False, 240.0, 22.0),
    "drawer-out": View(LID_OPEN_DEG, True, -48.0, 30.0),
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
    "nickel": (0.70, 0.70, 0.72),
    "rubber": (0.03, 0.03, 0.03),
    "black": (0.015, 0.015, 0.018),
    "moulded": (0.03, 0.03, 0.035),
    "bank": (0.025, 0.025, 0.028),
    "pcb-purple": (0.30, 0.08, 0.45),
    "pcb-tinyvga": (0.02, 0.12, 0.05),
    "vga-blue": (0.05, 0.15, 0.55),
    "silver": (0.75, 0.75, 0.77),
    "switch-red": (0.70, 0.05, 0.05),
    "display": (0.12, 0.12, 0.12),
    "led": (0.95, 0.85, 0.75),
}

#: Parts both routes share (``demobox.shared``): the distinct shared colour.
SHARED = ("hinge-base", "hinge-lid", "bezel", "bezel-clip", "retainer", "packing", "mt1-pin")

#: Render-only component heights above the PCB top (mm): not in the board data,
#: so guesses good enough to read as the part.  They are not used for any fit.
COMPONENT_H = {"pmod": 5.5, "usb_power": 3.2, "display7": 6.5, "switch": 4.0, "led": 0.8}

PATTERN_SIZE = (1024, 600)   # the 7" panel's native resolution


# --- transforms ---------------------------------------------------------------------

IDENTITY = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0]


def _loc_matrix(loc: cq.Location) -> list[float]:
    t = loc.wrapped.Transformation()
    m = [t.Value(r, c) for r in (1, 2, 3) for c in (1, 2, 3, 4)] + [0.0, 0.0, 0.0, 1.0]
    return [0.0 if abs(v) < 1e-12 else v for v in m]


def frame_matrix(lay: Layout, frame: str, lid_deg: float, drawer_mm: float) -> list[float]:
    """Row-major 4 x 4 moving ``frame``'s solids from their shut placement in
    the base frame (as ``body.assembly(route, 0, 0)`` gives them): the lid
    turned ``lid_deg`` open about the hinge axis (``lid_location(lid_deg)``
    after undoing ``lid_location(0)``), the drawer out ``drawer_mm`` along
    ``Layout.drawer_out``."""
    if frame == "base":
        return list(IDENTITY)
    if frame == "drawer":
        m = list(IDENTITY)
        m[3], m[7], m[11] = (v * drawer_mm for v in lay.drawer_out)
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
    """A board-frame box in the base frame (``demobox.layout``: a 180 degree
    turn about Z, ``base = (ox - bx, oy - by, oz + bz)``)."""
    ox, oy, oz = lay.board_origin
    return Box(ox - x1, oy - y1, oz + z0, ox - x0, oy - y0, oz + z1)


def _tube(a, b, r: float) -> cq.Shape:
    """A cable leg: cylinder of radius ``r`` from point ``a`` to ``b``, with a
    sphere at ``a`` so consecutive legs join without a gap at the corner."""
    va, vb = cq.Vector(*a), cq.Vector(*b)
    leg = cq.Solid.makeCylinder(r, (vb - va).Length, va, vb - va)
    return leg.fuse(cq.Solid.makeSphere(r, va, angleDegrees1=-90, angleDegrees2=90))


def vga_cable_path(lay: Layout, end: Box, monitor: str = body.ASSEMBLY_MONITOR):
    """The slim VGA cable's centre line, as ``(frame, [points])`` runs in the
    base frame with the lid shut.  From the top of the plug/adapter (``end``)
    it rises to the hinge axis and through the hinge cable channel (base run);
    in the lid it rises into the gutter, runs along the hinge gutter (and the side
    gutter for a side exit) and ends at the monitor's exit point
    (``checks._exit_point``) -- the route ``checks.cables_route`` budgets."""
    m = MONITORS[monitor]
    hy, hz = lay.hinge_axis
    ex, ey, ez = _exit_point(m, lay)
    ey, ez = hy + ey, hz + ez                       # lid frame -> base frame, lid shut
    cx, cy = (end.x0 + end.x1) / 2, (end.y0 + end.y1) / 2
    g = lay.hinge_cable_channel
    gx0 = (g.x0 + g.x1) / 2                          # the channel the cable threads
    hg = lay.lid_cable_gutters["hinge"]
    gy = hy + (hg.y0 + hg.y1) / 2                    # the hinge gutter's centre line
    base = [(cx, cy, end.z1), (cx, cy, hz), (gx0, hy, hz)]
    lid = [(gx0, hy, hz), (gx0, hy, ez), (gx0, gy, ez)]
    side = lay.lid_cable_gutters.get(exit_edge(m))
    if side is not None:                             # along the hinge gutter into the side one
        sx = (side.x0 + side.x1) / 2
        lid += [(sx, gy, ez), (sx, ey, ez)]
    else:
        lid += [(ex, gy, ez)]
    lid += [(ex, ey, ez)]
    return [("base", base), ("lid", lid)]


def vga_cable(lay: Layout, end: Box, monitor: str = body.ASSEMBLY_MONITOR):
    """``(name, solid, frame)`` for each leg of ``vga_cable_path``."""
    r = CABLES["vga-slim"].dia / 2
    out = []
    for frame, pts in vga_cable_path(lay, end, monitor):
        for i, (a, b) in enumerate(zip(pts, pts[1:])):
            if a != b:
                out.append((f"vga-cable-{frame}{i}", _tube(a, b, r), frame))
    return out


def tinyvga_boxes(lay: Layout, board: str = body.ASSEMBLY_BOARD) -> dict[str, Box]:
    """The TinyVGA's blocks in the base frame: ``pcb``, ``header``, ``de15``,
    the VGA ``plug`` body and (90 degree plug only) the ``adapter``; the plug
    and adapter together are ``TINYVGA.plug_keepout(VGA_PLUG_STRAIGHT)``."""
    dx, dy, dz = tinyvga_offset(board)

    def tv(b: Box) -> Box:
        m = b.moved(dx, dy, dz)
        return _to_base(lay, m.x0, m.y0, m.z0, m.x1, m.y1, m.z1)

    keep = TINYVGA.plug_keepout(VGA_PLUG_STRAIGHT)
    plug = replace(keep, y0=keep.y1 - TINYVGA.plug_body_len)
    out = {"pcb": tv(TINYVGA.pcb), "header": tv(TINYVGA.header), "de15": tv(TINYVGA.de15),
           "plug": tv(plug)}
    if not VGA_PLUG_STRAIGHT:
        out["adapter"] = tv(replace(keep, y1=plug.y0))
    return out


def bought_parts(lay: Layout, board: str = body.ASSEMBLY_BOARD):
    """Representative solids the assembly leaves out, in the base frame
    (lid shut): ``(name, solid, material, colour, frame)``; ``frame`` is the
    frame it moves with (``base``, or ``lid`` for the cable inside the lid)."""
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

    # TinyVGA in J13 (pmod3), placed by demobox.layout.tinyvga_offset
    tvb = tinyvga_boxes(lay, board)
    add("tinyvga-pcb", _box(tvb["pcb"]), "pcb", "pcb-tinyvga")
    add("tinyvga-header", _box(tvb["header"]), "plastic", "black")
    add("tinyvga-de15", _box(tvb["de15"]), "plastic", "vga-blue")
    add("vga-plug", _box(tvb["plug"]), "plastic", "moulded")
    if "adapter" in tvb:
        add("vga-adapter", _box(tvb["adapter"]), "plastic", "moulded")
    for name, solid, frame in vga_cable(lay, tvb.get("adapter", tvb["plug"])):
        add(name, solid, "rubber", "black", frame)

    # right-angle USB-C plug in J1, its cable dropping through the deck slot
    up = lay.board_keepouts[f"{board}/usb_plug"]
    add("usb-c-plug", _box(up), "plastic", "moulded")
    usb = CABLES["usb-c-right-angle"]
    ux, uy = (up.x0 + up.x1) / 2, up.y0 + usb.dia / 2 + 0.3
    z_end = lay.deck_z - lay.wall - 2 * usb.dia
    add("usb-c-cable", cq.Solid.makeCylinder(usb.dia / 2, up.z0 - z_end,
                                             cq.Vector(ux, uy, z_end)), "rubber", "black")
    return out


def screen_quad(lay: Layout, monitor: str = body.ASSEMBLY_MONITOR):
    """The monitor's active area with the lid shut, in the base frame (the
    lid frame + the hinge axis), like the part STLs: four corners (mm), image
    lower-left, lower-right, upper-right, upper-left, just in front of the
    panel face (``checks._panel_point``: panel u -> +x, v -> -y)."""
    m = MONITORS[monitor]
    pb = panel_in_lid(m, lay)
    (aw, ah), (au, av) = m.active, m.active_offset
    hy, hz = lay.hinge_axis
    z = hz + pb.z0 - 0.05
    x0, x1 = pb.x0 + au, pb.x0 + au + aw
    y_lo, y_hi = hy + pb.y1 - av, hy + pb.y1 - av - ah        # image bottom, image top
    return [[x0, y_lo, z], [x1, y_lo, z], [x1, y_hi, z], [x0, y_hi, z]]


# --- route scenes ------------------------------------------------------------------

def _bbox(s: cq.Shape) -> tuple[float, ...]:
    b = s.BoundingBox()
    return b.xmin, b.ymin, b.zmin, b.xmax, b.ymax, b.zmax


def _same(a, b) -> bool:
    return all(abs(p - q) < 1e-6 for p, q in zip(a, b))


def _material(route: str, name: str, laser_panels) -> tuple[str, tuple[float, float, float]]:
    if name.startswith("hw:foot"):
        return "rubber", PALETTE["rubber"]
    if name.startswith("hw:magnet"):
        return "metal", PALETTE["nickel"]
    if name.startswith("hw:"):
        return "metal", PALETTE["metal"]
    if name == "board":
        return "pcb", PALETTE["pcb-purple"]
    if name == "panel":                                     # the monitor body
        return "plastic", PALETTE["black"]
    if name == "monitor-driver":
        return "pcb", PALETTE["pcb-tinyvga"]
    if name == "bank":
        return "plastic", PALETTE["bank"]
    if name in laser_panels:
        return "plywood", PALETTE["plywood"]
    if name in SHARED or name.startswith("bezel-clip"):
        return "pla", PALETTE["pla-shared"]
    return "pla", PALETTE["pla"]


def _round_head(shape: cq.Shape) -> cq.Shape:
    """A screw head's box keep-out (the laser route's T-slot heads) as the
    round head it stands for: the cylinder inscribed in the box, its axis
    along the box's shortest side."""
    b = shape.BoundingBox()
    lo, size = (b.xmin, b.ymin, b.zmin), (b.xlen, b.ylen, b.zlen)
    ax = min(range(3), key=lambda i: size[i])
    r = min(size[i] for i in range(3) if i != ax) / 2
    base = [lo[i] + size[i] / 2 for i in range(3)]
    base[ax] = lo[ax]
    d = [0.0, 0.0, 0.0]
    d[ax] = 1.0
    return cq.Solid.makeCylinder(r, size[ax], cq.Vector(*base), cq.Vector(*d))


def _write_stl(shape: cq.Shape, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(cq.Workplane("XY").add(shape), str(path), "STL",
                        tolerance=STL_TOLERANCE, angularTolerance=STL_ANGULAR)


def route_parts(route: str, out: Path) -> list[dict]:
    """Write ``route``'s part STLs under ``out/<route>/``; return each part's
    ``{part, file, frame, material, colour}``."""
    lay = layout(ROUTES[route])
    shut = body.assembly(route, 0.0, 0.0)
    names = [n for n, _, _ in shut]
    if len(set(names)) != len(names):
        raise ValueError(f"{route}: assembly part names are not unique")
    lid_moved = {n: _bbox(s) for n, s, _ in body.assembly(route, LID_OPEN_DEG, 0.0)}
    drawer_moved = {n: _bbox(s) for n, s, _ in body.assembly(route, 0.0, lay.drawer_travel)}
    laser_panels = set()
    if route == "laser":
        from demobox.laser import panels as P
        laser_panels = set(P.build(lay, lay.wall, P.KERF).panels)
    parts = []
    for name, shape, _colour in shut:
        bb = _bbox(shape)
        frame = ("lid" if not _same(bb, lid_moved[name]) else
                 "drawer" if not _same(bb, drawer_moved[name]) else "base")
        material, colour = _material(route, name, laser_panels)
        if name.startswith("hw:head-"):
            shape = _round_head(shape)
        parts.append((name, shape, frame, material, colour))
    parts += [(n, s, frame, mat, c) for n, s, mat, c, frame in bought_parts(lay)]
    entries = []
    for name, shape, frame, material, colour in parts:
        rel = Path(route) / f"{name.replace(':', '_')}.stl"
        _write_stl(shape, out / rel)
        entries.append({"part": name, "file": str(rel), "frame": frame,
                        "material": material, "colour": list(colour)})
    return entries


def view_manifest(route: str, view: str, entries: list[dict], pattern: str) -> dict:
    lay = layout(ROUTES[route])
    v = VIEWS[view]
    drawer_mm = lay.drawer_travel if v.drawer else 0.0
    parts = [{**e, "transform": frame_matrix(lay, e["frame"], v.lid_deg, drawer_mm)}
             for e in entries]
    screen = {"part": "screen", "quad": screen_quad(lay), "image": pattern,
              "transform": frame_matrix(lay, "lid", v.lid_deg, drawer_mm)}
    return {"name": f"{route}-{view}", "route": route, "view": view, "lid_deg": v.lid_deg,
            "drawer_out_mm": drawer_mm, "monitor": body.ASSEMBLY_MONITOR,
            "bank": body.ASSEMBLY_BANK, "board": body.ASSEMBLY_BOARD,
            "camera": {"azimuth_deg": v.azimuth_deg, "elevation_deg": v.elevation_deg,
                       "lens_mm": LENS_MM},
            "resolution": list(RESOLUTION), "samples": SAMPLES,
            "parts": parts, "screens": [screen]}


# --- flat pack ---------------------------------------------------------------------

def flatpack(out: Path) -> dict:
    """Every laser panel lying flat (its own (u, v) in the XY plane, 3 mm
    thick), shelf-packed in rows with FLATPACK_GAP between them."""
    from demobox.laser import panels as P
    lay = layout(ROUTES["laser"])
    pans = P.build(lay, lay.wall, P.KERF).panels
    flat = {}
    for name, pn in pans.items():
        u0, v0, u1, v1 = pn.shape.bounds
        s = replace(pn, normal="z", z0=0.0).solid().translate(cq.Vector(-u0, -v0, 0.0))
        flat[name] = (s, u1 - u0, v1 - v0)
    area = sum((w + FLATPACK_GAP) * (h + FLATPACK_GAP) for _, w, h in flat.values())
    row_w = max(max(w for _, w, _ in flat.values()), math.sqrt(area * 4 / 3) * 1.05)
    order = sorted(flat, key=lambda n: (-flat[n][2], -flat[n][1], n))
    x = y = row_h = 0.0
    parts = []
    for name in order:
        s, w, h = flat[name]
        if x > 0 and x + w > row_w:
            x, y, row_h = 0.0, y + row_h + FLATPACK_GAP, 0.0
        rel = Path("flatpack") / f"{name}.stl"
        _write_stl(s, out / rel)
        m = list(IDENTITY)
        m[3], m[7] = x, y
        parts.append({"part": name, "file": str(rel), "frame": "flat", "material": "plywood",
                      "colour": list(PALETTE["plywood"]), "transform": m})
        x += w + FLATPACK_GAP
        row_h = max(row_h, h)
    az, el = FLATPACK_VIEW
    return {"name": "laser-flatpack", "route": "laser", "view": "flatpack",
            "camera": {"azimuth_deg": az, "elevation_deg": el, "lens_mm": LENS_MM},
            "resolution": list(RESOLUTION), "samples": SAMPLES, "parts": parts,
            "screens": []}


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
        for v in views:
            write(view_manifest(route, v, entries, pattern))
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
