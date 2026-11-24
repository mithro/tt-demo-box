"""The shared layout: where everything sits, derived from the part data.

One layout, two bodies: the printed route calls ``layout(2.4)``, the laser
route ``layout(3.0)``.  ``verify.py`` proves the fits from the same numbers.
Every placement below is computed from ``demobox.parts``; the only numbers
typed here are the spec's (``LID_OPEN_DEG`` .. ``CLOSED_CLEARANCE``), the
machine beds, ``SLACK`` and a few named design choices.  The box is sized for
one kit (``DESIGN_MONITOR``, ``DESIGN_BANK``, both board revisions): every
dimension is that kit plus ``SLACK`` plus the walls, and nothing else.

Frames
------
Base frame: origin at the front-left-bottom outside corner of the base; X to
the visitor's right, Y away from the visitor (towards the hinge), Z up.  Every
``Box``/``Cyl`` field of ``Layout`` is in the base frame except ``lid_outer``,
``monitor_space``, ``lid_strip`` and (when ``boost_in_lid``) ``boost_pocket``.

Lid frame: the base frame translated to the hinge axis, i.e. origin at
(x = 0, y = hinge y, z = hinge z), axes parallel to the base's.  The axis is
on the seam (z = ``rim_z``), so closed, the lid lies above z = 0 and mostly in
front of the axis (Y < 0; its back ``KNUCKLE_R`` is behind it).  The lid's
inside face is up at z = ``lid_outer.z1 - wall``; the monitor hangs from it,
screen down.  Opening turns the lid about the axis (parallel to X) so the
front edge rises and goes back: ``lid_location(a)`` / ``lid_profile_yz(a)``
give it at ``a`` degrees open (0 closed, 100 at the stop).

Board placement
---------------
The submodule's ``BoardSpec`` frame is a top view from the component side,
Y up (``tools.schema``; ``tools.kicad_extract.frame`` flips KiCad's Y-down).
In the box the board is component side up (not mirrored), turned +90 degrees
about Z so that its long run -- J1's USB-C plug, the board, the TinyVGA and
its VGA plug -- lies along X, J1 at -X and the Pmod edge (board y = 0) with
the TinyVGA at +X:

    base = (ox - by, oy + bx, oz + bz),   (ox, oy, oz) = ``board_origin``.

Base rows
---------
* **Board row (front).**  Both revisions' keep-outs (``"<rev>/envelope"``,
  ``"<rev>/usb_plug"``, ``"<rev>/tinyvga"``) are placed together; their union
  starts at ``wall + SLACK`` in X and in Y.  The row is that union plus
  ``SLACK`` at each X end.  The TinyVGA keep-out is its PCB, its DE-15 and a
  left/right-angle 90 degree VGA adapter (``vga_adapter`` is always True,
  spec Decision 3, ruling R16a): ``CABLES["vga-90-adapter"].plug`` = 35 along
  the D-sub's long axis (base Y), 17 out of the DE-15 face (base +X), 20 tall,
  its socket on its end face towards the bank row (base +Y; assumed, see the
  cable's Source).  The monitor's VGA plug goes into that socket from +Y:
  ``"<rev>/vga_plug"`` is the plug (``PLUG_BODY_LEN``) and its stiff
  ``STRAIGHT_RUN``, along +Y into the bank row's +X back corner, its hood
  ``plug_width`` across X.
* **Bank row (behind),** starting ``SLACK`` behind the board row, ``bank W +
  2*SLACK`` deep.  Along X from the left wall: ``port_room`` (by J1, so the
  bank-to-board cable is short; long enough for the longest bank-side plug +
  SLACK, and at least ``FINGERTIP_D`` for the bank's end button), then
  ``bank_bay`` (the bank + SLACK each side).  The VGA plug's keep-out sits
  in the row's +X back corner (where the board puts it; it must clear the
  bay and end within the row).  ``boost_pocket`` (the boost module + SLACK
  each side) goes on the floor in room the bay and the plug leave -- between
  them, or past the plug -- along X or turned 90 degrees (R10 as amended by
  R16a); if none is left it goes in ``lid_strip`` (``boost_in_lid``).
* **Width** = max(board row, port room + bay, the VGA plug's keep-out +
  SLACK, monitor W + 2*SLACK) + 2*wall.
  **Depth** = wall + SLACK + board row Y + SLACK + bank row Y + SLACK + wall,
  and at least monitor H + 2*SLACK + 2*wall + CATCH_BLOCK.
* **Height.**  ``rim_z = wall + max(bank H, board stack H) + SLACK``; the
  board stack is the keep-out union's z extent.  The board stands on
  ``plinth`` (floor to PCB underside), lifted so the union's top is at
  ``rim_z - SLACK``: level with the rim, in view over the front wall.  The
  plinth covers both revisions' PCB outlines.  ``plinth_relief`` is the notch
  cut from it under a J1 plug that hangs below the PCB underside over the
  plinth (v3.2's, under v3.3's longer PCB): the plug's footprint + FIT, down
  from the plinth top to FIT below the plug.  (The TinyVGA is past the Pmod
  edge, off the plinth.)  ``outer`` is the base only: ``outer.z1 == rim_z``.
* **Pins.**  ``pins["MT2"]`` is the fixed pin both revisions share;
  ``pins["<rev>/MT1"]`` is where the one loose pin goes for that revision (the
  plinth has a ``PEG_HOLE_D`` hole at each).  Each is ``PEG_DIA``, from the
  plinth top to ``PIN_PROUD`` above that revision's PCB top.

Lid
---
A tray over the base footprint, ``wall + TAPE_T + monitor depth +
CLOSED_CLEARANCE`` deep.  The monitor is taped to the inside face, centred
in X, against the free (front) edge wall -- or, when the lid's catch blocks
reach over it in X (a box barely wider than the monitor), ``CATCH_BLOCK``
behind that wall, past them -- cable edge towards the hinge:
``monitor_space`` is the panel plus SLACK each side in X and Y, its depth
exactly the panel's, its face ``CLOSED_CLEARANCE`` above the seam.
``lid_strip`` is the rest of the inside, between the monitor and the
hinge-end wall; it carries the cables and, if ``boost_in_lid``, the boost
module (against the inside face, at the strip's -X monitor-side corner).

Hinge and catch
---------------
The hinge axis is on the seam, ``KNUCKLE_R`` in from the back face, so the
knuckles stay inside base + lid.  ``hinge_notch`` is the gap in the knuckle
line on the VGA plug's run axis (the pigtail drops straight to it there; in
the lid it runs over from the monitor's exit), the pigtail's diameter
(``CABLES["monitor-pigtail"]``) + 2*FIT wide; the plug does not pass, the
cable is threaded first.  ``hinge_relief_r`` is the radius about the axis
within which the hinge's two kinds of segment are relieved (ruling R11): the
furthest any lid point that enters the base's YZ profile, at any angle of
``sweep_angles()``, gets from the axis, plus FIT.  Along X there are three
kinds of segment (ruling R15): lid-knuckle (the base cut back to
``hinge_relief_r``, the lid whole), base-knuckle (the lid cut back, the base
keeps a ``KNUCKLE_R`` knuckle) and open (both cut back).  Knuckles go only in
``knuckle_x``: the X ranges with no ``base_contents`` within ``hinge_relief_r``
of the axis in YZ, less the notch.
``lid_catch`` is two magnets under the front rim, each in a ``CATCH_BLOCK``
block against the inside of the front wall, at the X nearest its front
corner where the block clears every board-row keep-out in XY.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.schema import Source

from demobox.geom import Box, Cyl
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import BOARD_KEYS, board_envelope, board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS, Monitor
from demobox.parts.tinyvga import TINYVGA

# --- spec values, verbatim -------------------------------------------------
LID_OPEN_DEG = 100.0
FIT = 0.5                 # slip / threading clearance, per side
CLOSED_CLEARANCE = 2.0    # monitor face above the tallest thing in the base
PRINT_BED = (220.0, 220.0)
LASER_BED = (300.0, 200.0)
#: The two build routes and their wall thickness: printed shell, 3 mm plywood.
ROUTES: dict[str, float] = {"printed": 2.4, "laser": 3.0}
#: Room left round each thing in the box, per side (spec Goal 1).
SLACK = 1.0

# --- the kit (spec Decision 1) -------------------------------------------------
DESIGN_MONITOR = "taobao-tim"
DESIGN_BANK = "xiaomi-pb2020"
#: Plugs that can sit at the bank's port end: the box's own USB-C or USB-A
#: cable into a socket bank, or a bank's built-in cable.
BANK_SIDE_PLUGS = ("usb-c-right-angle", "usb-a-c", "bank-built-in")

# --- design choices ----------------------------------------------------------
#: Hinge knuckle radius (``demobox.shared.hinge`` uses this one).
KNUCKLE_R = 4.0
#: Hinge knuckle length along X (``demobox.shared.hinge`` uses this one).
KNUCKLE_LEN = 10.0
#: The bought hinge rod: "3 mm steel rod or 2.85 mm filament".
PIN_ROD_D = 3.0
#: Disc magnets (6 x 3 mm, bought) and the lid catch built from them: a pair
#: under the base's front rim and in the lid's front rim, MAGNET_RECESS below
#: each seam face, so the shut lid's magnets face each other 2 x MAGNET_RECESS
#: apart.  Each sits in a CATCH_BLOCK square, CATCH_BLOCK_H tall block against
#: the front wall (a 2.4 or 3 mm wall can't hold a 6 mm magnet).
MAGNET_D = 6.0
MAGNET_T = 3.0
MAGNET_RECESS = 0.2
CATCH_BLOCK = 10.0
CATCH_BLOCK_H = 6.0
#: Board locating pins, into the boards' 3.2 mm MT1/MT2 holes.
PEG_DIA = 3.0
#: The plinth's hole for the loose MT1 pin: PEG_DIA plus a slip clearance, so
#: the pin pushes in by hand and comes out again for the other revision.
PEG_HOLE_D = PEG_DIA + 0.2
#: How far the board pins stand above the PCB top.  Closed, the board can
#: lift only together with its TinyVGA and plug, whose top is SLACK +
#: CLOSED_CLEARANCE below the monitor face; the pins are 1 mm longer than
#: that, so they never leave the board's holes.
PIN_PROUD = CLOSED_CLEARANCE + SLACK + 1.0
#: A fingertip on a bank's end button (the port room is at least this long).
FINGERTIP_D = 16.0

# --- placeholders (UNCONFIRMED) ------------------------------------------------
#: J1 axis above the PCB top: a top-mount USB-C receptacle's 3.2 mm shell / 2.
USB_C_AXIS_ABOVE_PCB = 1.6
#: TinyVGA PCB underside relative to the host PCB underside when plugged in:
#: a right-angle header into a right-angle socket leaves the two PCBs
#: about coplanar.
TINYVGA_Z_OFFSET = 0.0
#: Double-sided foam tape (VHB type) between the monitor's back and the lid.
TAPE_T = 1.0

#: (name, value, source) for verify.py to report as UNCONFIRMED.
UNCONFIRMED: tuple[tuple[str, float, Source], ...] = (
    ("USB_C_AXIS_ABOVE_PCB", USB_C_AXIS_ABOVE_PCB, Source(
        "Placeholder: J1 axis height", "demobox/layout.py",
        "Typical top-mount USB-C; measure J1 on a v3.2/v3.3 board.")),
    ("TINYVGA_Z_OFFSET", TINYVGA_Z_OFFSET, Source(
        "Placeholder: TinyVGA height when plugged into J13", "demobox/layout.py",
        "Assumed coplanar with the host PCB; measure a plugged-in TinyVGA.")),
    ("TAPE_T", TAPE_T, Source(
        "Placeholder: foam tape thickness", "docs/superpowers/specs/2026-11-24-compact-box-design.md",
        "Decision 3: VHB-type double-sided foam tape; 1.0 mm is typical, "
        "measure the tape bought.")),
)

_USB = CABLES["usb-c-right-angle"]   # bank to board, right-angle at J1
_PIGTAIL = CABLES["monitor-pigtail"]  # the monitor's own VGA cable (ruling R13)
_BOOST = CABLES["usb-12v-boost"]
_ADAPTER = CABLES["vga-90-adapter"]  # R16a: left/right-angle type (assumed; UNCONFIRMED)


# --- board-frame keep-outs ---------------------------------------------------

def _usb_plug(key: str) -> Box:
    """The right-angle USB-C plug in J1, board frame: out past the shell's
    overhang along board +y.  Its cable leaves the far end sideways, towards
    the bank row (board +x, base +Y): the shortest run to the bank, and the
    way ``checks.usb_path`` routes it."""
    spec = board_spec(key)
    j1 = next(f for f in spec.features if f.kind == "usb_power")
    length, width, height = _USB.plug
    cx = (j1.x0 + j1.x1) / 2
    cz = spec.outline.thickness + USB_C_AXIS_ABOVE_PCB
    return Box(cx - width / 2, j1.y1, cz - height / 2,
               cx + width / 2, j1.y1 + length, cz + height / 2, f"{key} J1 USB-C plug")


def tinyvga_offset(key: str) -> tuple[float, float, float]:
    """``(dx, dy, dz)`` moving the TinyVGA from its own frame to where it sits
    in J13 (pmod3) of board ``key``, board frame: centred on the socket, its
    PCB edge fully inserted at the socket mouth, lifted ``TINYVGA_Z_OFFSET``."""
    pmod = next(p for p in board_spec(key).pmods if p.key == "pmod3")
    h = TINYVGA.header
    return ((pmod.body_x0 + pmod.body_x1) / 2 - (h.x0 + h.x1) / 2,
            pmod.body_y0, TINYVGA_Z_OFFSET)


def _adapter_frame() -> Box:
    """R16a: the left/right-angle 90 degree VGA adapter on the DE-15, TinyVGA
    frame: ``_ADAPTER.plug`` = (35 along the D-sub's long axis, 17 out of the
    DE-15 face, 20 tall), centred on the socket and on the plug's axis."""
    span, out, tall = _ADAPTER.plug
    d = TINYVGA.de15
    cx, zc = (d.x0 + d.x1) / 2, (TINYVGA.plug_z0 + TINYVGA.plug_z1) / 2
    return Box(cx - span / 2, d.y0 - out, zc - tall / 2, cx + span / 2, d.y0, zc + tall / 2,
               "VGA 90 degree adapter")


def _vga_plug_frame() -> Box:
    """R16a: the monitor's VGA plug in the adapter's socket, on the adapter's
    end face towards the bank row (TinyVGA +x, base +Y), and its stiff
    ``STRAIGHT_RUN`` behind it, TinyVGA frame.  The plug's hood (``plug_width``
    wide, ``plug_z0..plug_z1``) is centred on the adapter's mid-depth."""
    a, t = _adapter_frame(), TINYVGA
    yc = (a.y0 + a.y1) / 2
    return Box(a.x1, yc - t.plug_width / 2, t.plug_z0,
               a.x1 + t.plug_body_len + t.straight_run, yc + t.plug_width / 2, t.plug_z1,
               "VGA plug + stiff run")


def _tinyvga(key: str) -> Box:
    """TinyVGA PCB + DE-15 + the 90 degree adapter in J13 (pmod3), board frame."""
    u = TINYVGA.pcb.union(TINYVGA.de15).union(_adapter_frame())
    return Box(u.x0, u.y0, u.z0, u.x1, u.y1, u.z1,
               f"{key} TinyVGA + adapter").moved(*tinyvga_offset(key))


#: The board-row parts; ``vga_plug`` lies in the bank row's +X back corner.
ROW_PARTS = ("envelope", "usb_plug", "tinyvga")


def _board_frame(key: str) -> dict[str, Box]:
    return {"envelope": board_envelope(key),
            "usb_plug": _usb_plug(key),
            "tinyvga": _tinyvga(key),
            "vga_plug": _vga_plug_frame().moved(*tinyvga_offset(key))}


def _union(boxes) -> Box:
    boxes = list(boxes)
    u = boxes[0]
    for b in boxes[1:]:
        u = u.union(b)
    return u


def _row_board_frame() -> Box:
    """Both revisions' board-row keep-outs (not the VGA plug), board frame."""
    return _union(b for k in BOARD_KEYS for part, b in _board_frame(k).items()
                  if part in ROW_PARTS)


def _to_base(b: Box, origin: tuple[float, float, float], what: str) -> Box:
    """Board-frame box to the base frame: base = (ox - by, oy + bx, oz + bz)."""
    ox, oy, oz = origin
    return Box(ox - b.y1, oy + b.x0, oz + b.z0, ox - b.y0, oy + b.x1, oz + b.z1, what)


def _board_keepouts(origin: tuple[float, float, float]) -> dict[str, Box]:
    """Both revisions' keep-outs in the base frame, keyed ``"<rev>/<part>"``."""
    return {f"{k}/{part}": _to_base(b, origin, f"{k} {part}")
            for k in BOARD_KEYS for part, b in _board_frame(k).items()}


def exit_edge(m: Monitor) -> str:
    """The panel edge (front view, upright) the monitor's cables leave by.  A
    bare kit's connectors are on its driver board; its cables are taken out at
    the hinge end ("bottom"), the shortest way to the hinge."""
    if m.cable_edge is not None:
        return m.cable_edge
    if m.connector_exit in ("left", "right", "top", "bottom"):
        return m.connector_exit
    return "bottom"


# --- the layout --------------------------------------------------------------

@dataclass(frozen=True)
class Layout:
    wall: float
    outer: Box                       # the base; outer.z1 == rim_z
    rim_z: float                     # the seam
    board_origin: tuple[float, float, float]
    board_keepouts: dict[str, Box]   # "<rev>/envelope", "<rev>/usb_plug", "<rev>/tinyvga",
                                     # "<rev>/vga_plug" (in the bank row's +X back corner)
    vga_adapter: bool                # R16a: always True, the 90 degree VGA adapter
    plinth: Box                      # floor to the PCB underside
    plinth_relief: Box               # notch in the plinth under the v3.2 J1 plug
    pins: dict[str, Cyl]             # "MT2" (fixed), "<rev>/MT1" (the loose pin's places)
    bank_bay: Box
    port_room: Box
    boost_pocket: Box                # base frame, or lid frame (closed) if boost_in_lid
    boost_in_lid: bool
    hinge_axis: tuple[float, float]  # (y, z)
    hinge_notch: Box
    hinge_relief_r: float            # R11: knuckle-segment relief radius about the axis
    lid_outer: Box                   # lid frame, closed
    monitor_space: Box               # lid frame, closed
    lid_strip: Box                   # lid frame, closed
    lid_catch: tuple[Cyl, ...]       # the base-side catch magnets
    #: R15: the X ranges where a knuckle may go: no base content
    #: (``base_contents``) within ``hinge_relief_r`` of the axis in YZ, and
    #: not the pigtail's notch.  Everywhere else is an open segment.
    knuckle_x: tuple[tuple[float, float], ...] = ()

    def catch_base_block(self, c: Cyl) -> Box:
        """The block holding catch magnet ``c`` under the base's rim (base frame)."""
        h, w = self.rim_z, self.wall
        return Box(c.cx - CATCH_BLOCK / 2, w, h - CATCH_BLOCK_H, c.cx + CATCH_BLOCK / 2,
                   w + CATCH_BLOCK, h, "lid catch block (base)")

    def catch_lid_block(self, c: Cyl) -> Box:
        """The block over it in the lid's front rim (lid frame, closed)."""
        b = self.catch_base_block(c)
        d = self.hinge_axis[0]
        return Box(b.x0, b.y0 - d, 0.0, b.x1, b.y1 - d, CATCH_BLOCK_H, "lid catch block (lid)")

    def catch_lid_magnet(self, c: Cyl) -> Cyl:
        """The lid-side magnet facing ``c`` across the seam (lid frame, closed)."""
        return Cyl(c.cx, c.cy - self.hinge_axis[0], MAGNET_RECESS, MAGNET_RECESS + MAGNET_T,
                   MAGNET_D / 2, "lid catch magnet (lid)")

    def _open_yz(self, y: float, z: float, angle_deg: float) -> tuple[float, float]:
        """Lid-frame (y, z) to base-frame (Y, Z) with the lid ``angle_deg`` open:
        a turn of -angle about +X (front edge up and back), then the axis offset."""
        hy, hz = self.hinge_axis
        a = math.radians(-angle_deg)
        return (hy + y * math.cos(a) - z * math.sin(a),
                hz + y * math.sin(a) + z * math.cos(a))

    def lid_profile_yz(self, angle_deg: float):
        """The lid's side profile (YZ, base frame) at ``angle_deg`` open."""
        from shapely.geometry import Polygon
        o = self.lid_outer
        corners = ((o.y0, o.z0), (o.y1, o.z0), (o.y1, o.z1), (o.y0, o.z1))
        return Polygon([self._open_yz(y, z, angle_deg) for y, z in corners])

    def lid_location(self, angle_deg: float):
        """``cq.Location`` placing lid-frame solids in the base frame at
        ``angle_deg`` open (the same transform as ``lid_profile_yz``)."""
        import cadquery as cq
        hy, hz = self.hinge_axis
        return (cq.Location(cq.Vector(0.0, hy, hz))
                * cq.Location(cq.Vector(0.0, 0.0, 0.0), cq.Vector(1.0, 0.0, 0.0), -angle_deg))


def sweep_angles() -> list[float]:
    """Every whole degree from 0 to LID_OPEN_DEG, and the stop itself."""
    angles = [float(a) for a in range(0, int(math.floor(LID_OPEN_DEG)) + 1)]
    if angles[-1] != LID_OPEN_DEG:
        angles.append(float(LID_OPEN_DEG))
    return angles


def _hinge_relief_r(lid: Box, base: Box, hy: float, hz: float) -> float:
    """R11: the furthest from the axis (hy, hz) any lid point gets while
    inside the base's YZ profile, over ``sweep_angles()``, plus FIT.  The lid
    profile turned to each angle is clipped to the base's; the clip is convex,
    so its furthest point from the axis is a vertex."""
    from shapely.geometry import Polygon, box as sbox
    region = sbox(base.y0, base.z0, base.y1, base.z1)
    corners = ((lid.y0, lid.z0), (lid.y1, lid.z0), (lid.y1, lid.z1), (lid.y0, lid.z1))
    far = 0.0
    for a in sweep_angles():
        t = math.radians(-a)
        prof = Polygon([(hy + y * math.cos(t) - z * math.sin(t), hz + y * math.sin(t) + z * math.cos(t))
                        for y, z in corners])
        inside = prof.intersection(region)
        if inside.area > 0:
            far = max(far, max(math.hypot(y - hy, z - hz) for y, z in inside.exterior.coords))
    return far + FIT


def base_contents(lay: Layout) -> dict[str, Box]:
    """Everything in the base a lid or knuckle must miss, base frame: the
    board keep-outs, the plinth, the pins (as boxes), the design bank as
    packed (centred in the bay), the boost module's pocket (when in the base),
    the port room (the bank cables' room) and the catch blocks."""
    b = BATTERIES[DESIGN_BANK]
    bay = lay.bank_bay
    l_, w, h = b.size
    x0, y0 = (bay.x0 + bay.x1 - l_) / 2, (bay.y0 + bay.y1 - w) / 2
    out = dict(lay.board_keepouts)
    out["plinth"] = lay.plinth
    out.update({k: Box(p.cx - p.r, p.cy - p.r, p.z0, p.cx + p.r, p.cy + p.r, p.z1, p.what)
                for k, p in lay.pins.items()})
    out[f"bank {b.key}"] = Box(x0, y0, bay.z0, x0 + l_, y0 + w, bay.z0 + h, f"bank {b.key}")
    if not lay.boost_in_lid:
        out["boost pocket"] = lay.boost_pocket
    out["port room"] = lay.port_room
    for i, c in enumerate(lay.lid_catch, 1):
        out[f"lid catch block {i}"] = lay.catch_base_block(c)
    return out


def _yz_distance(b: Box, y: float, z: float) -> float:
    return math.hypot(max(b.y0 - y, 0.0, y - b.y1), max(b.z0 - z, 0.0, z - b.z1))


def _knuckle_x(lay: Layout) -> tuple[tuple[float, float], ...]:
    """R15: X 0..width less every base content within ``hinge_relief_r`` of
    the axis in YZ, and less the pigtail's notch."""
    hy, hz = lay.hinge_axis
    blocked = [(b.x0, b.x1) for b in base_contents(lay).values()
               if _yz_distance(b, hy, hz) <= lay.hinge_relief_r]
    blocked.append((lay.hinge_notch.x0, lay.hinge_notch.x1))
    ranges, x = [], lay.outer.x0
    for a, b in sorted(blocked):
        if a > x:
            ranges.append((x, a))
        x = max(x, b)
    if x < lay.outer.x1:
        ranges.append((x, lay.outer.x1))
    return tuple(ranges)


def _catch_x0(keepouts: dict[str, Box], wall: float, width: float, from_left: bool) -> float:
    """The x0 of the catch block nearest its front corner whose footprint
    (front wall inside, CATCH_BLOCK square) clears every keep-out in XY."""
    lo, hi = wall, width - wall
    y0, y1 = wall, wall + CATCH_BLOCK
    x0 = lo if from_left else hi - CATCH_BLOCK
    while True:
        hits = [k for k in keepouts.values()
                if k.x0 < x0 + CATCH_BLOCK and x0 < k.x1 and k.y0 < y1 and y0 < k.y1]
        if not hits:
            return x0
        x0 = max(k.x1 for k in hits) if from_left else min(k.x0 for k in hits) - CATCH_BLOCK
        if x0 < lo or x0 + CATCH_BLOCK > hi:
            names = ", ".join(sorted(k.what for k in hits))
            raise ValueError(f"no room for the {'left' if from_left else 'right'} lid catch "
                             f"block along the front wall: blocked by {names}")


def layout(wall: float, bank: str = DESIGN_BANK, monitor: str = DESIGN_MONITOR) -> Layout:
    b = BATTERIES[bank]
    m = MONITORS[monitor]
    if exit_edge(m) != "bottom" or m.pigtail_exit_u is None:
        raise ValueError(f"monitor {monitor!r} has no pigtail exit on its bottom edge: "
                         "only a taped design-kit monitor can be laid out")
    mw, mh, md = m.panel

    # --- board row (the adapter always fitted, R16a) -------------------------
    u = _row_board_frame()
    board_row_x = u.size[1] + 2 * SLACK          # board y runs along base X
    board_row_y = u.size[0]
    stack_h = u.size[2]
    # the VGA plug and its stiff run, relative to the board row's start (base X
    # wall + SLACK at board y u.y1): base X = wall + SLACK + u.y1 - board y
    vp = [_vga_plug_frame().moved(*tinyvga_offset(k)) for k in BOARD_KEYS]
    plug_x0 = SLACK + u.y1 - max(v.y1 for v in vp)     # from the inside of the left wall
    plug_x1 = SLACK + u.y1 - min(v.y0 for v in vp)

    # --- bank row ---------------------------------------------------------------
    port_len = max(max(CABLES[k].plug[0] for k in BANK_SIDE_PLUGS) + SLACK, FINGERTIP_D)
    bay_x, bay_y = b.size[0] + 2 * SLACK, b.size[1] + 2 * SLACK
    if plug_x0 < port_len + bay_x:
        raise ValueError(f"the VGA plug keep-out (X {plug_x0:.2f}..{plug_x1:.2f} inside the "
                         f"wall) runs into the bank bay (to {port_len + bay_x:.2f})")
    boost = tuple(d + 2 * SLACK for d in _BOOST.plug)

    # --- outer ------------------------------------------------------------------
    inner_x = max(board_row_x, port_len + bay_x, plug_x1 + SLACK, mw + 2 * SLACK)
    width = inner_x + 2 * wall
    depth = max(wall + SLACK + board_row_y + SLACK + bay_y + SLACK + wall,
                mh + 2 * SLACK + 2 * wall + CATCH_BLOCK)
    rim_z = wall + max(b.size[2], stack_h) + SLACK
    outer = Box(0.0, 0.0, 0.0, width, depth, rim_z, "base")

    # R10 as amended by R16a: the boost on the floor in bank-row room the bay
    # and the plug leave (between them, or past the plug), along X or turned;
    # else in the lid strip
    base_room_z = rim_z - wall
    zones = ((port_len + bay_x, plug_x0), (plug_x1, inner_x))
    boost_at = next(((wall + z0, fx, fy) for z0, z1 in zones
                     for fx, fy in ((boost[0], boost[1]), (boost[1], boost[0]))
                     if fx <= z1 - z0 + 1e-9 and fy <= bay_y + 1e-9
                     and boost[2] <= base_room_z + 1e-9), None)
    boost_in_lid = boost_at is None

    # --- board on its plinth -------------------------------------------------
    # union: base X from wall + SLACK, base Y from wall + SLACK, top at rim - SLACK
    origin = (wall + SLACK + u.y1, wall + SLACK - u.x0, rim_z - SLACK - u.z1)
    ox, oy, oz = origin
    keepouts = _board_keepouts(origin)
    specs = {k: board_spec(k) for k in BOARD_KEYS}
    # both revisions' PCB outlines (board x 0..W, y 0..H)
    pcb = Box(0.0, 0.0, 0.0, max(s.outline.width for s in specs.values()),
              max(s.outline.height for s in specs.values()), 0.0)
    p = _to_base(pcb, origin, "")
    plinth = Box(p.x0, p.y0, wall, p.x1, p.y1, max(oz, wall), "board plinth")
    # J1 plugs hanging below the PCB underside over the plinth (v3.2's plug,
    # under v3.3's longer PCB): notched out, FIT round and below them
    hanging = [keepouts[f"{k}/usb_plug"] for k in BOARD_KEYS]
    hanging = [h for h in hanging if h.z0 < plinth.z1
               and h.x0 < plinth.x1 and plinth.x0 < h.x1 and h.y0 < plinth.y1 and plinth.y0 < h.y1]
    if len(hanging) != 1:
        raise ValueError(f"expected one J1 plug over the plinth, found {len(hanging)}")
    h = hanging[0]
    plinth_relief = Box(h.x0 - FIT, h.y0 - FIT, h.z0 - FIT, h.x1 + FIT, h.y1 + FIT, plinth.z1,
                        f"plinth relief ({h.what})")

    def pin(h, key: str, what: str) -> Cyl:
        top = oz + specs[key].outline.thickness + PIN_PROUD
        return Cyl(ox - h.y, oy + h.x, plinth.z1, top, PEG_DIA / 2, what)

    holes = {k: {h.label: h for h in s.holes} for k, s in specs.items()}
    mt2 = {(holes[k]["MT2"].x, holes[k]["MT2"].y) for k in BOARD_KEYS}
    tops = {s.outline.thickness for s in specs.values()}
    if len(mt2) != 1 or len(tops) != 1:
        raise ValueError(f"the revisions do not share MT2 {mt2} and PCB thickness {tops}: "
                         "one fixed pin can't serve both")
    k0 = BOARD_KEYS[0]
    pins = {"MT2": pin(holes[k0]["MT2"], k0, "MT2 pin (fixed)")}
    for k in BOARD_KEYS:
        pins[f"{k}/MT1"] = pin(holes[k]["MT1"], k, f"{k} MT1 pin (loose)")

    # --- bank row: port room, bay, boost ---------------------------------------
    row_y0 = oy + u.x1 + SLACK
    port_room = Box(wall, row_y0, wall, wall + port_len, row_y0 + bay_y, rim_z, "port room")
    bank_bay = Box(port_room.x1, row_y0, wall, port_room.x1 + bay_x, row_y0 + bay_y, rim_z,
                   "bank bay")

    # --- lid catch -----------------------------------------------------------
    xs = (_catch_x0(keepouts, wall, width, True), _catch_x0(keepouts, wall, width, False))
    if xs[0] + CATCH_BLOCK > xs[1]:
        raise ValueError(f"the lid catch blocks overlap along the front wall: x0 = {xs}")
    catch = tuple(Cyl(x + CATCH_BLOCK / 2, wall + CATCH_BLOCK / 2,
                      rim_z - MAGNET_RECESS - MAGNET_T, rim_z - MAGNET_RECESS, MAGNET_D / 2,
                      f"lid catch magnet (base) {i + 1}") for i, x in enumerate(xs))

    # --- hinge and lid (lid frame, closed) --------------------------------------
    hy, hz = depth - KNUCKLE_R, rim_z
    lid_h = wall + TAPE_T + md + CLOSED_CLEARANCE
    lid_outer = Box(0.0, -hy, 0.0, width, depth - hy, lid_h, "lid")
    in_z1 = lid_h - wall                          # the inside face (tape side)
    ms_x0 = (width - (mw + 2 * SLACK)) / 2
    # against the front wall, unless the catch blocks in the lid's front rim
    # reach over the monitor in X: then just behind them
    over = any(x < ms_x0 + mw + 2 * SLACK and ms_x0 < x + CATCH_BLOCK for x in xs)
    ms_y0 = lid_outer.y0 + wall + (CATCH_BLOCK if over else 0.0)
    monitor_space = Box(ms_x0, ms_y0, CLOSED_CLEARANCE, ms_x0 + mw + 2 * SLACK,
                        ms_y0 + mh + 2 * SLACK, in_z1 - TAPE_T, f"monitor space ({monitor})")
    lid_strip = Box(wall, monitor_space.y1, 0.0, width - wall, lid_outer.y1 - wall, in_z1,
                    "lid strip")

    if boost_in_lid:
        boost_pocket = Box(lid_strip.x0, lid_strip.y0, in_z1 - boost[2],
                           lid_strip.x0 + boost[0], lid_strip.y0 + boost[1], in_z1,
                           "boost converter pocket (lid)")
        if boost_pocket.y1 > lid_strip.y1 or boost_pocket.z0 < lid_strip.z0:
            raise ValueError(f"boost module {_BOOST.plug} does not fit the lid strip "
                             f"{lid_strip.size}")
    else:
        bx0, fx, fy = boost_at
        boost_pocket = Box(bx0, row_y0, wall, bx0 + fx, row_y0 + fy, wall + boost[2],
                           "boost converter pocket")

    plugs = [keepouts[f"{k}/vga_plug"] for k in BOARD_KEYS]
    if max(p.y1 for p in plugs) > bank_bay.y1:
        raise ValueError(f"the VGA plug's stiff run (to Y {max(p.y1 for p in plugs):.2f}) "
                         f"runs past the bank row (to {bank_bay.y1:.2f})")
    # the notch on the plug's run axis: the pigtail drops straight to it there
    exit_x = (plugs[0].x0 + plugs[0].x1) / 2
    half = _PIGTAIL.dia / 2 + FIT
    hinge_notch = Box(exit_x - half, hy - KNUCKLE_R, hz - KNUCKLE_R,
                      exit_x + half, hy + KNUCKLE_R, hz + KNUCKLE_R, "hinge notch (pigtail)")
    hinge_relief_r = _hinge_relief_r(lid_outer, outer, hy, hz)

    lay = Layout(
        wall=wall, outer=outer, rim_z=rim_z, board_origin=origin,
        board_keepouts=keepouts, vga_adapter=True, plinth=plinth,
        plinth_relief=plinth_relief, pins=pins,
        bank_bay=bank_bay, port_room=port_room, boost_pocket=boost_pocket,
        boost_in_lid=boost_in_lid, hinge_axis=(hy, hz), hinge_notch=hinge_notch,
        hinge_relief_r=hinge_relief_r,
        lid_outer=lid_outer, monitor_space=monitor_space, lid_strip=lid_strip,
        lid_catch=catch)
    return replace(lay, knuckle_x=_knuckle_x(lay))
