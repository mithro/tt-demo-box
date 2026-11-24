"""Tiny Tapeout demo boards (v3.2, v3.3) and the generic Pmod peripheral type.

Everything about the boards comes from the submodule's
``tinytapeout.boards.BOARDS``; nothing is retyped here.

Frame: ``board_envelope`` is in *board coordinates*, exactly the submodule's
``BoardSpec`` frame: origin at the PCB's lower-left corner viewed from the
component side, X right, Y up (Pmod edge at Y = 0, so the Pmod sockets overhang
to negative Y), Z up from the PCB underside (Z = 0).
"""

from __future__ import annotations

from dataclasses import dataclass

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tinytapeout.boards import BOARDS
from tools.schema import BoardSpec, Source

from demobox.geom import Box

BOARD_KEYS: tuple[str, ...] = ("v3.2", "v3.3")

#: Tallest component above the PCB underside.  Placeholder: the spec lists this
#: as an open measurement, so ``verify.py`` reports it UNCONFIRMED.
TALLEST_COMPONENT: float = 12.0
TALLEST_COMPONENT_CONFIRMED: bool = False
TALLEST_COMPONENT_SOURCE = Source(
    label="Placeholder tallest component",
    ref="docs spec, open measurements",
    note="12 mm is a guess to be replaced by measuring a populated board.")


def board_spec(key: str) -> BoardSpec:
    if key not in BOARD_KEYS:
        raise KeyError(f"unsupported board {key!r}; the box supports {BOARD_KEYS}")
    return BOARDS[key]


def board_envelope(key: str) -> Box:
    """PCB outline + Pmod bodies' overhang + USB-C shell, Z 0..TALLEST_COMPONENT."""
    spec = board_spec(key)
    xs = [0.0, spec.outline.width]
    ys = [0.0, spec.outline.height]
    for p in spec.pmods:
        xs += [p.body_x0, p.body_x1]
        ys += [p.body_y0, p.body_y1]
    for f in spec.features:
        if f.kind == "usb_power":
            xs += [f.x0, f.x1]
            ys += [f.y0, f.y1]
    return Box(min(xs), min(ys), 0.0, max(xs), max(ys), TALLEST_COMPONENT,
               f"board {key} envelope")


@dataclass(frozen=True)
class PmodBoard:
    """A peripheral that plugs into a Pmod host (frame: see the part's module)."""

    key: str
    pcb: Box
    de15: Box
    header: Box
    sources: tuple[Source, ...]
    confirmed: bool
    plug_body_len: float
    straight_run: float
    angled_run: float
    plug_width: float
    plug_z0: float
    plug_z1: float

    def plug_keepout(self, straight: bool) -> Box:
        """Space a DE-15 plug and its cable need, continuing outward from the
        socket face (``de15.y0``): plug body plus 40 mm straight or 20 mm with a
        90 degree adapter."""
        length = self.plug_body_len + (self.straight_run if straight else self.angled_run)
        cx = (self.de15.x0 + self.de15.x1) / 2
        return Box(cx - self.plug_width / 2, self.de15.y0 - length, self.plug_z0,
                   cx + self.plug_width / 2, self.de15.y0, self.plug_z1,
                   f"{self.key} plug keepout ({'straight' if straight else '90deg'})")
