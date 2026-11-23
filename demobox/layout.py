"""The shared layout: where everything sits, derived from the part data.

One layout, two bodies: the printed route calls ``layout(2.4)``, the laser
route ``layout(3.0)``.  ``verify.py`` proves the fits from the same numbers.
Every placement below is computed from ``demobox.parts``; the only numbers
typed here are the spec's (``LID_OPEN_DEG`` .. ``CLOSED_CLEARANCE``), the
machine bed, and a few named design choices.

Frames
------
Base frame: origin at the front-left-bottom outside corner of the base; X to
the visitor's right, Y away from the visitor (towards the hinge), Z up.  Every
``Box``/``Cyl`` field of ``Layout`` is in the base frame except ``lid_outer``
and ``lid_pocket``.

Lid frame: the base frame translated to the hinge axis, i.e. origin at
(x = 0, y = hinge y, z = hinge z), axes parallel to the base's.  Closed, the
lid lies in front of and above the axis (Y <= 0, Z >= 0); its screen face is
Z = 0, facing down onto the deck.  Opening turns it about the axis (parallel to
X) so the front edge rises and goes back: ``lid_location(a)`` /
``lid_profile_yz(a)`` give it at ``a`` degrees open (0 closed, 100 at the stop).

Board placement
---------------
The submodule's ``BoardSpec`` frame is a top view from the component side,
Y up (``tools.schema``; ``tools.kicad_extract.frame`` flips KiCad's Y-down).
On the deck the board is component side up with its Pmod edge (board y = 0)
towards the hinge, so board y maps to base -Y.  Keeping it un-mirrored then
forces board x to base -X: a 180 degree turn about Z,

    base = (ox - bx, oy - by, oz + bz),   (ox, oy, oz) = ``board_origin``.

J1 (board x 70.9..81.5, the y-max edge) therefore lands at the **front-left**
of the board (the plan's "front-right" line had the turn wrong).

Drawer
------
The bank drawer slides out of the base's left side, along -X
(``drawer_out``).  From the drawer face inward: face wall, ``cable_bay``
(CABLE_BAY long), ``bay`` (BAY_INSIDE), back wall.  Each bank lies L along X,
W along Y (centred by its packing insert), on the bay floor, with its port end
at the cable-bay boundary, so its end button faces the finger hole in the
drawer face.  ``drawer_travel`` takes the longest bank fully outside the base
while the drawer's back stays in its runners; the USB cables stay plugged in
and pay out from a slack loop in the deck cavity above the drawer.

Lid
---
The common pocket is the largest monitor insert (panel + INSERT_MATERIAL each
side + FIT each side) and at least LID_POCKET_MIN.  Its depth is the deepest
insert stack plus FIT.  Monitors mount buttons-down, so a panel's bottom edge
faces the hinge end.

Cable gutters (R13) give every monitor's cables an in-lid route to the hinge
cable channel: ``lid_cable_gutters["hinge"]`` runs across the lid between the
pocket and the hinge-end wall, and a side gutter (``"left"``/``"right"``) runs
beside the pocket on each side some monitor's cable leaves by, joining the
hinge gutter.  They are as deep as the pocket and open to it.  Each is at
least the monitor-side cable bundle (``lid_cable_bundle``: VGA + DC lead, side
by side) + FIT wide; where a cable leaves a panel edge square into a gutter
and must turn along it, the gutter is widened so the turn keeps the bundle's
bend radius, counting the room the insert leaves beside the panel (a side-exit
monitor's insert pushes its panel to the far side: ``checks.panel_in_lid``).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.schema import Source

from demobox.geom import Box, Cyl, Stadium
from demobox.parts.batteries import BATTERIES
from demobox.parts.board import BOARD_KEYS, board_envelope, board_spec
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS, Monitor
from demobox.parts.tinyvga import TINYVGA

# --- spec values, verbatim -------------------------------------------------
LID_OPEN_DEG = 100.0
BAY_INSIDE = (158.0, 82.0, 34.0)
CABLE_BAY = 35.0
LID_POCKET_MIN = (185.0, 120.0)
FIT = 0.5                 # insert / slide clearance, per side
CLOSED_CLEARANCE = 2.0    # lid underside above the tallest thing on the deck
PRINT_BED = (220.0, 220.0)
LASER_BED = (300.0, 200.0)
#: M3 heat-set insert in printed parts: hole diameter and depth.
HEATSET_HOLE_D = 4.0
HEATSET_DEPTH = 5.7
#: The two build routes and their wall thickness: printed shell, 3 mm plywood.
ROUTES: dict[str, float] = {"printed": 2.4, "laser": 3.0}

# --- design choices ----------------------------------------------------------
#: The VGA plug is sized for a 90 degree adapter: with a straight plug the base
#: would be deeper than the print bed (``_base_depth(2.4, straight=True)``).
VGA_PLUG_STRAIGHT = False
#: Monitor insert material: front bezel plate and rear retainer thickness.
INSERT_MATERIAL = 1.2
#: Bare-kit driver board standoff height above the panel's back.
DRIVER_STANDOFF = 5.0
#: Deck standoff minimum: an M3 heat-set insert (HEATSET_DEPTH) from the top,
#: rounded up to the whole millimetre (a floor under the insert).
STANDOFF_MIN = float(math.ceil(HEATSET_DEPTH))
#: MT1 locating peg: into the board's 3.2 mm hole, below the PCB's top face.
PEG_DIA = 3.0
PEG_HEIGHT = 1.2
#: The boss's hole for the loose pin: PEG_DIA plus a slip clearance, so the
#: pin pushes in by hand and comes out again for the other revision.
PEG_HOLE_D = PEG_DIA + 0.2
#: Finger hole in the drawer face, around the bank's end button.
FINGER_HOLE_D = 20.0

# --- placeholders for part heights not in any source (UNCONFIRMED) -----------
#: J1 axis above the PCB top: a top-mount USB-C receptacle's 3.2 mm shell / 2.
USB_C_AXIS_ABOVE_PCB = 1.6
#: TinyVGA PCB underside relative to the host PCB underside when plugged in:
#: a right-angle header into a right-angle socket leaves the two PCBs
#: about coplanar.
TINYVGA_Z_OFFSET = 0.0

#: (name, value, source) for verify.py to report as UNCONFIRMED.
UNCONFIRMED: tuple[tuple[str, float, Source], ...] = (
    ("USB_C_AXIS_ABOVE_PCB", USB_C_AXIS_ABOVE_PCB, Source(
        "Placeholder: J1 axis height", "demobox/layout.py",
        "Typical top-mount USB-C; measure J1 on a v3.2/v3.3 board.")),
    ("TINYVGA_Z_OFFSET", TINYVGA_Z_OFFSET, Source(
        "Placeholder: TinyVGA height when plugged into J13", "demobox/layout.py",
        "Assumed coplanar with the host PCB; measure a plugged-in TinyVGA.")),
)

_USB = CABLES["usb-c-right-angle"]   # bank to board, right-angle at J1
_VGA = CABLES["vga-slim"]
_BOOST = CABLES["usb-12v-boost"]


def insert_stack(m: Monitor) -> float:
    """Depth of a monitor's insert stack: bezel plate + panel (+ driver board
    on standoffs, for bare kits) + rear retainer."""
    depth = INSERT_MATERIAL + m.panel[2] + INSERT_MATERIAL
    if m.driver is not None:
        depth += DRIVER_STANDOFF + m.driver.z1
    return depth


# --- board-frame keep-outs ---------------------------------------------------

def _usb_plug(key: str) -> Box:
    """The right-angle USB-C plug in J1, board frame: out past the shell's
    overhang along board +y, its cable leaving downward at the far end."""
    spec = board_spec(key)
    j1 = next(f for f in spec.features if f.kind == "usb_power")
    length, width, height = _USB.plug
    cx = (j1.x0 + j1.x1) / 2
    cz = spec.outline.thickness + USB_C_AXIS_ABOVE_PCB
    return Box(cx - width / 2, j1.y1, cz - height / 2,
               cx + width / 2, j1.y1 + length, cz + height / 2, f"{key} J1 USB-C plug")


def _tinyvga(key: str, straight: bool) -> Box:
    """TinyVGA PCB + DE-15 + VGA plug keep-out in J13 (pmod3), board frame."""
    pmod = next(p for p in board_spec(key).pmods if p.key == "pmod3")
    h = TINYVGA.header
    dx = (pmod.body_x0 + pmod.body_x1) / 2 - (h.x0 + h.x1) / 2
    dy = pmod.body_y0           # fully inserted: PCB edge at the socket mouth
    u = TINYVGA.pcb.union(TINYVGA.de15).union(TINYVGA.plug_keepout(straight))
    return Box(u.x0, u.y0, u.z0, u.x1, u.y1, u.z1,
               f"{key} TinyVGA + VGA plug").moved(dx, dy, TINYVGA_Z_OFFSET)


def _board_frame(key: str, straight: bool) -> dict[str, Box]:
    return {"envelope": board_envelope(key),
            "usb_plug": _usb_plug(key),
            "tinyvga": _tinyvga(key, straight)}


def _union(boxes) -> Box:
    boxes = list(boxes)
    u = boxes[0]
    for b in boxes[1:]:
        u = u.union(b)
    return u


def _all_board_frame(straight: bool) -> Box:
    return _union(b for k in BOARD_KEYS for b in _board_frame(k, straight).values())


def _to_base(b: Box, origin: tuple[float, float, float], what: str) -> Box:
    ox, oy, oz = origin
    return Box(ox - b.x1, oy - b.y1, oz + b.z0, ox - b.x0, oy - b.y0, oz + b.z1, what)


# --- base footprint ----------------------------------------------------------

def _pocket_xy() -> tuple[float, float]:
    px = max(m.panel[0] + 2 * INSERT_MATERIAL + 2 * FIT for m in MONITORS.values())
    py = max(m.panel[1] + 2 * INSERT_MATERIAL + 2 * FIT for m in MONITORS.values())
    if px < LID_POCKET_MIN[0] or py < LID_POCKET_MIN[1]:
        raise ValueError(f"lid pocket {px} x {py} is below LID_POCKET_MIN {LID_POCKET_MIN}")
    return px, py


def exit_edge(m: Monitor) -> str:
    """The panel edge (front view, upright) the monitor's cables leave by.  A
    bare kit's connectors are on its driver board; its cables are taken out at
    the hinge end ("bottom"), the shortest way to the hinge channel."""
    if m.cable_edge is not None:
        return m.cable_edge
    if m.connector_exit in ("left", "right", "top", "bottom"):
        return m.connector_exit
    return "bottom"


def lid_cable_bundle() -> tuple[float, float]:
    """(width, bend radius) of the monitor-side cables in the lid, side by
    side: the VGA cable plus, for 12 V monitors, the boost cable's DC lead."""
    cables = [_VGA] + ([_BOOST] if any(m.power_in == "12V-boost" for m in MONITORS.values())
                       else [])
    return sum(c.dia for c in cables), max(c.min_bend_r for c in cables)


def _gutter_widths() -> dict[str, float]:
    """Width of each lid cable gutter (see the module docstring)."""
    px, _ = _pocket_xy()
    d, r = lid_cable_bundle()
    run = d + FIT
    turn = r + d / 2 + FIT             # panel edge to the gutter's far side
    edges = {exit_edge(m) for m in MONITORS.values()}
    # a bottom exit's panel sits FIT + INSERT_MATERIAL off the pocket's hinge end
    widths = {"hinge": max(run, turn - (FIT + INSERT_MATERIAL)) if "bottom" in edges else run}
    for m in MONITORS.values():
        e = exit_edge(m)
        if e in ("left", "right"):
            room = px - FIT - INSERT_MATERIAL - m.panel[0]   # panel pushed to the far side
            widths[e] = max(widths.get(e, run), turn - room)
    return widths


def _lid_inner_xy() -> tuple[float, float]:
    """Pocket plus cable gutters, the lid's inside footprint."""
    px, py = _pocket_xy()
    g = _gutter_widths()
    return px + g.get("left", 0.0) + g.get("right", 0.0), py + g["hinge"]


def _drawer_depth(wall: float) -> float:
    """Base Y the drawer needs: base wall, FIT, drawer wall, bay, and back."""
    return BAY_INSIDE[1] + 2 * (2 * wall + FIT)


def _base_width(wall: float, straight: bool) -> float:
    u = _all_board_frame(straight)
    return max(u.size[0] + 2 * (wall + FIT),
               # drawer face (it is the base's left wall there), cable bay, bay,
               # drawer back wall, FIT, base right wall
               CABLE_BAY + BAY_INSIDE[0] + 3 * wall + FIT,
               _lid_inner_xy()[0] + 2 * wall)


def _base_depth(wall: float, straight: bool) -> float:
    u = _all_board_frame(straight)
    return max(u.size[1] + 2 * (wall + FIT),
               _drawer_depth(wall),
               _lid_inner_xy()[1] + 2 * wall)


# --- the layout --------------------------------------------------------------

@dataclass(frozen=True)
class Layout:
    wall: float
    outer: Box
    deck_z: float
    board_origin: tuple[float, float, float]
    board_keepouts: dict[str, Box]   # "<rev>/envelope", "<rev>/usb_plug", "<rev>/tinyvga"
    standoffs: tuple[Cyl, ...]       # screwed, M3 heat-set insert (shared MT2)
    mt1_boss: Stadium                # merged boss under both MT1s, no insert
    pegs: dict[str, Cyl]             # per revision: locating peg into MT1
    supports: tuple[Cyl, ...]        # plain edge-support pads, no insert
    usb_slot: Box
    bay: Box
    cable_bay: Box
    drawer_face_hole: Box
    drawer_out: tuple[float, float, float]
    drawer_travel: float
    boost_pocket: Box
    hinge_axis: tuple[float, float]  # (y, z)
    hinge_cable_channel: Box
    lid_outer: Box                   # lid frame, closed
    lid_pocket: Box                  # lid frame, closed
    lid_cable_gutters: dict[str, Box]  # lid frame, closed: "hinge", and "left"/"right"

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


def layout(wall: float) -> Layout:
    straight = VGA_PLUG_STRAIGHT
    width = _base_width(wall, straight)
    depth = _base_depth(wall, straight)

    # --- drawer: front of the base, sliding out of the left side -------------
    bay_y0 = wall + FIT + wall
    bay_z0 = wall + wall                     # base floor + drawer floor
    cable_bay = Box(wall, bay_y0, bay_z0, wall + CABLE_BAY, bay_y0 + BAY_INSIDE[1],
                    bay_z0 + BAY_INSIDE[2], "drawer cable bay")
    bay = Box(cable_bay.x1, bay_y0, bay_z0, cable_bay.x1 + BAY_INSIDE[0],
              bay_y0 + BAY_INSIDE[1], bay_z0 + BAY_INSIDE[2], "battery bay")
    longest = max(b.size[0] for b in BATTERIES.values())
    drawer_travel = bay.x0 + longest + FIT

    buttons = [(bay.y0 + (BAY_INSIDE[1] - b.size[1]) / 2 + b.button[1], bay.z0 + b.button[2])
               for b in BATTERIES.values() if b.button is not None and b.button[0] == "end"]
    r = FINGER_HOLE_D / 2
    drawer_face_hole = Box(0.0, min(y for y, _ in buttons) - r, min(z for _, z in buttons) - r,
                           wall, max(y for y, _ in buttons) + r, max(z for _, z in buttons) + r,
                           "drawer face finger hole")

    # --- deck: over the drawer and the USB-C cable's drop --------------------
    cavity = _USB.min_bend_r + _USB.dia      # right-angle drop turning flat
    deck_z = bay.z1 + FIT + cavity + wall

    # --- board on the deck ----------------------------------------------------
    frames = {k: _board_frame(k, straight) for k in BOARD_KEYS}
    u = _all_board_frame(straight)
    standoff_h = max(STANDOFF_MIN, -u.z0 + FIT)
    ox = width / 2 + (u.x0 + u.x1) / 2         # keep-outs centred across the deck
    oy = wall + FIT + u.y1                     # front-most keep-out FIT off the front wall
    origin = (ox, oy, deck_z + standoff_h)
    keepouts = {f"{k}/{part}": _to_base(b, origin, f"{k} {part}")
                for k, parts in frames.items() for part, b in parts.items()}
    height = origin[2] + u.z1 + CLOSED_CLEARANCE
    outer = Box(0.0, 0.0, 0.0, width, depth, height, "base")

    # Under-board supports, all with their tops at the board underside:
    #  * ``standoffs``: screwed, with an M3 heat-set insert -- the holes both
    #    revisions share (MT2);
    #  * ``mt1_boss``: one merged stadium boss under the revisions' MT1 holes,
    #    which differ by 5 mm (too close for two inserted bosses), no insert;
    #  * ``pegs``: a locating peg per revision rising from the boss into that
    #    revision's MT1 hole.  Each revision's peg sits under the other
    #    revision's PCB, so a fixed pair would lift either board: the boss has a
    #    PEG_HOLE_D hole at each MT1 and only the fitted revision's peg (a loose
    #    printed pin) is pushed in;
    #  * ``supports``: plain pads at the other two corners of the hole
    #    rectangle (clear of J1), so two fixings do not let the board rock.
    def at(x, y):
        return ox - x, oy - y

    std_r = max(h.keepout_dia for k in BOARD_KEYS for h in board_spec(k).holes) / 2
    holes: dict[tuple[float, float], list[str]] = {}
    for k in BOARD_KEYS:
        for h in board_spec(k).holes:
            holes.setdefault((h.x, h.y), []).append(f"{k} {h.label}")
    shared = {xy: names for xy, names in holes.items() if len(names) == len(BOARD_KEYS)}
    standoffs = tuple(Cyl(*at(x, y), deck_z, origin[2], std_r, "standoff " + ", ".join(n))
                      for (x, y), n in shared.items())
    mt1 = {k: next(h for h in board_spec(k).holes if h.label == "MT1") for k in BOARD_KEYS}
    ends = sorted(at(h.x, h.y) for h in mt1.values())
    mt1_boss = Stadium(*ends[0], *ends[-1], std_r, deck_z, origin[2], "MT1 boss (no insert)")
    pegs = {k: Cyl(*at(h.x, h.y), origin[2], origin[2] + PEG_HEIGHT, PEG_DIA / 2,
                   f"{k} MT1 locating peg") for k, h in mt1.items()}
    mt2 = next(h for h in board_spec(BOARD_KEYS[0]).holes if h.label == "MT2")
    j1_y0 = min(f.y0 for k in BOARD_KEYS for f in board_spec(k).features
                if f.kind == "usb_power")
    supports = (
        Cyl(*at(min(h.x for h in mt1.values()), mt2.y), deck_z, origin[2], std_r,
            "edge support (Pmod corner)"),
        Cyl(*at(mt2.x, j1_y0 - std_r - FIT), deck_z, origin[2], std_r,
            "edge support (J1 corner)"),
    )

    # USB-C slot: under both revisions' plug cable ends
    plugs = [keepouts[f"{k}/usb_plug"] for k in BOARD_KEYS]
    usb_slot = Box(min(p.x0 for p in plugs) - FIT, min(p.y0 for p in plugs) - FIT,
                   deck_z - wall,
                   max(p.x1 for p in plugs) + FIT, max(p.y0 for p in plugs) + _USB.dia + FIT,
                   deck_z, "deck USB-C slot")

    # boost converter body: on the base floor behind the drawer, at the left
    bl, bw, bh = _BOOST.plug
    by0 = bay.y1 + wall + FIT
    boost_pocket = Box(wall + FIT, by0, wall, wall + FIT + bl + 2 * FIT,
                       by0 + bw + 2 * FIT, wall + bh + FIT, "boost converter pocket")

    # --- hinge and lid ---------------------------------------------------------
    hinge = (depth, height)                   # back-top edge of the base
    px, py = _pocket_xy()
    pocket_depth = max(insert_stack(m) for m in MONITORS.values()) + FIT
    lid_depth = pocket_depth + wall
    lid_outer = Box(0.0, -depth, 0.0, width, 0.0, lid_depth, "lid")
    gw = _gutter_widths()
    inner_x = _lid_inner_xy()[0]
    in_x0 = (width - inner_x) / 2
    p_x0 = in_x0 + gw.get("left", 0.0)
    p_y1 = -wall - gw["hinge"]
    lid_pocket = Box(p_x0, p_y1 - py, 0.0, p_x0 + px, p_y1, pocket_depth, "lid pocket")
    gutters = {"hinge": Box(in_x0, p_y1, 0.0, in_x0 + inner_x, -wall, pocket_depth,
                            "lid hinge-end cable gutter")}
    if "left" in gw:
        gutters["left"] = Box(in_x0, lid_pocket.y0, 0.0, p_x0, p_y1, pocket_depth,
                              "lid left cable gutter")
    if "right" in gw:
        gutters["right"] = Box(lid_pocket.x1, lid_pocket.y0, 0.0, lid_pocket.x1 + gw["right"],
                               p_y1, pocket_depth, "lid right cable gutter")

    vga = keepouts[f"{BOARD_KEYS[0]}/tinyvga"]
    cx = (vga.x0 + vga.x1) / 2
    chan_w = _VGA.plug[1] + _BOOST.dia + 2 * FIT  # VGA plug threads through, beside the 12 V lead
    bend = max(_VGA.min_bend_r, _BOOST.min_bend_r)
    hinge_cable_channel = Box(cx - chan_w / 2, hinge[0] - bend, deck_z,
                              cx + chan_w / 2, hinge[0], hinge[1] + pocket_depth,
                              "hinge cable channel")

    return Layout(
        wall=wall, outer=outer, deck_z=deck_z, board_origin=origin,
        board_keepouts=keepouts, standoffs=standoffs, mt1_boss=mt1_boss, pegs=pegs,
        supports=supports, usb_slot=usb_slot,
        bay=bay, cable_bay=cable_bay, drawer_face_hole=drawer_face_hole,
        drawer_out=(-1.0, 0.0, 0.0), drawer_travel=drawer_travel,
        boost_pocket=boost_pocket, hinge_axis=hinge,
        hinge_cable_channel=hinge_cable_channel,
        lid_outer=lid_outer, lid_pocket=lid_pocket, lid_cable_gutters=gutters)
