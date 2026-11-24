"""7-inch VGA monitors: Tim's car monitor and two close variants.

Frame: ``panel`` is (W, H, T) of the body seen from the front, upright; the
panel's lower-left is the origin of ``active_offset`` and ``button``.  ``driver``
(bare kits only) is in the panel's BACK lower-left frame: x right, y up, z
rearward from the back face.  ``cable_edge`` is the edge, viewed from the
front, upright, where an edge connector or hard-wired pigtail leaves.

Sources: ``docs/superpowers/specs/monitor-survey.md`` (items H, J) and
``docs/measurements/2026-11-23-photo-measurements.md`` (Tim's unit, read off
photos, +/-2 mm).  Only 7" monitors are supported (Tim, 2026-11-23); monitors
with rear-facing sockets are out of scope, so ``connector_exit`` has no "rear".
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from tools.schema import Source

from demobox.geom import Box

Edge = Literal["left", "right", "top", "bottom"]

_SURVEY = "docs/superpowers/specs/monitor-survey.md"
_PHOTOS = "docs/measurements/2026-11-23-photo-measurements.md"

#: Common 7" 16:9 TN panel active area (AT070TN92 / 1024x600 class).
ACTIVE_7IN = (154.2, 85.9)


@dataclass(frozen=True)
class Monitor:
    key: str
    #: Short code for drawing names (``TDB-INS-<code>``): upper-case letters
    #: and digits, unique among MONITORS.
    code: str
    title: str
    kind: Literal["kit", "cased"]
    panel: tuple[float, float, float]
    active: tuple[float, float]
    active_offset: tuple[float, float]
    driver: Box | None
    connector_exit: Literal["left", "right", "top", "bottom", "pigtail", "board"]
    power_in: Literal["5V", "12V-boost"]
    button: tuple[float, float] | None
    sources: tuple[Source, ...]
    confirmed: bool
    cable_edge: Edge | None = None
    #: The cased monitor's own bezel opening (W, H); None for bare kits.
    window: tuple[float, float] | None = None
    #: Bare kits: the driver board's PCB thickness.  The PCB is the
    #: panel-side face of ``driver`` (z 0 .. driver_pcb_t); its components
    #: stand rearward of it, up to ``driver.z1``.
    driver_pcb_t: float | None = None
    #: Bare kits: the driver board's M3 mounting holes (x, y), in the panel's
    #: back frame like ``driver``.
    driver_holes: tuple[tuple[float, float], ...] = ()
    #: Cable length from the panel edge to the VGA plug's face; None means
    #: "not taped in the design kit; reported only".
    pigtail_len: float | None = None
    #: Where the cable leaves ``cable_edge``, measured from the panel's left in
    #: the front view with the cable edge at the bottom.
    pigtail_exit_u: float | None = None


def _centred_x(panel_w: float, active_w: float) -> float:
    return round((panel_w - active_w) / 2, 2)


_TAOBAO_TIM = Monitor(
    key="taobao-tim",
    code="T7",
    title="Tim's 7-inch car-style 'TFT color monitor' (Taobao)",
    kind="cased",
    # T is unmeasured: 20.0 is survey item H's rim depth, a placeholder.
    panel=(182, 118, 20.0),
    active=ACTIVE_7IN,
    # centred sideways; the button strip makes the bottom bezel the deeper one
    active_offset=(_centred_x(182, ACTIVE_7IN[0]), 18.0),
    driver=None,
    connector_exit="pigtail",
    power_in="12V-boost",
    # power button on the bottom long edge's front face; position read roughly
    # off photos 1, 2, 5 (buttons along that edge, IR window at the cable corner)
    button=(60.0, 8.0),
    sources=(
        Source("Tim's photos (back, face-down)", _PHOTOS,
               "Back ~182 x ~117-118 mm (photo 11); front ~176-181 x ~113 (photo 5); "
               "screen window ~159 x ~86 (photo 5). Good to +/-2 mm."),
        Source("Taobao listing size", "docs/superpowers/specs/2026-11-23-tt-demo-box-design.md",
               "Monitors table, row T: \"listing: 170 x 113 mm, 800x480 or 1024x600\" "
               "(smaller than the photo reading used for `panel`)."),
        Source("Cable and buttons", _PHOTOS,
               "Hard-wired cable leaves the long edge on the button side near the "
               "IR-window corner (photos 1, 2, 11); VGA + DC barrel + composite. "
               "Buttons: power, VOL, MENU, -, + along that edge."),
        Source("Placeholder: depth, active offset, button position", _PHOTOS,
               "Measure depth with calipers (20.0 is item H's rim depth); measure the "
               "active-area offset in the bezel and each button's position on the front."),
        Source("Placeholder: pigtail length and exit point", _PHOTOS,
               "Not measured: 300 mm cable length and 167 mm exit position from the "
               "panel's left are guesses read off photos 1, 2, 11; measure both."),
        Source("Stand clip taken off", "docs/superpowers/specs/2026-11-24-compact-box-design.md",
               "Decision 3: the monitor is taped to the lid with its stand clip taken off."),
    ),
    confirmed=False,
    cable_edge="bottom",
    window=(159, 86),
    pigtail_len=300.0,
    pigtail_exit_u=167.0,
)

_CAR_7 = Monitor(
    key="car-7-aliexpress",
    code="C7",
    title="7-inch plastic car-style TFT monitor (AliExpress 1005004614276566)",
    kind="cased",
    panel=(173, 113, 20),
    active=ACTIVE_7IN,
    active_offset=(_centred_x(173, ACTIVE_7IN[0]), 15.0),
    driver=None,
    connector_exit="right",
    power_in="12V-boost",
    button=(55.0, 7.0),
    sources=(
        Source("Survey item H", _SURVEY,
               "7\" plastic car-style TFT monitor, 1024x600, VGA/HDMI/AV, 12 V; "
               "173 x 113 x 20 at the rim + rear hump; connectors on the right side of "
               "the hump; AliExpress 1005004614276566, AU$39.79."),
        Source("Placeholder: active offset, button, bezel window", _SURVEY,
               "Not in the listing. Measure the active-area offset, the button "
               "position and the connector side on a real unit."),
    ),
    confirmed=False,
    cable_edge="right",
    window=(159, 86),
)

#: PCB800099 mounting holes: assumed one in from each corner by this much.
_KIT_HOLE_INSET = 3.5
_KIT_DRIVER = Box(37.0, 17.0, 0.0, 37.0 + 90.6, 17.0 + 65.7, 12.0, "PCB800099 driver board")

_KIT = Monitor(
    key="kit-at070tn92",
    code="K7",
    title="AT070TN92 7-inch 800x480 panel + PCB800099 driver board (bare kit)",
    kind="kit",
    panel=(165, 100, 5.7),
    active=ACTIVE_7IN,
    active_offset=(_centred_x(165, ACTIVE_7IN[0]), round((100 - ACTIVE_7IN[1]) / 2, 2)),
    # board in the panel's back frame; 12 mm height is a placeholder
    driver=_KIT_DRIVER,
    connector_exit="board",
    power_in="12V-boost",
    button=None,   # keypad is a separate board on a ribbon
    sources=(
        Source("Survey item J", _SURVEY,
               "AT070TN92 + PCB800099, 7\", 800x480, HDMI/VGA/2xAV, 12 V; board "
               "90.6 x 65.7; AliExpress 1005006369001145, AU$22.79."),
        Source("Placeholder: panel size, board position and height", _SURVEY,
               "Panel ~165 x 100 x 5.7 is unconfirmed, as are the board's offset, "
               "its height (12 mm) and the connector positions. Measure a real kit."),
        Source("Placeholder: driver PCB thickness, face and mounting holes", _SURVEY,
               "PCB assumed 1.6 mm, on the panel side of the board with its parts "
               "rearward, and M3 holes 3.5 mm in from each corner. Measure a real "
               "PCB800099."),
    ),
    confirmed=False,
    driver_pcb_t=1.6,
    driver_holes=tuple((x, y) for x in (_KIT_DRIVER.x0 + _KIT_HOLE_INSET,
                                        _KIT_DRIVER.x1 - _KIT_HOLE_INSET)
                       for y in (_KIT_DRIVER.y0 + _KIT_HOLE_INSET,
                                 _KIT_DRIVER.y1 - _KIT_HOLE_INSET)),
)

MONITORS: dict[str, Monitor] = {m.key: m for m in (_TAOBAO_TIM, _CAR_7, _KIT)}
