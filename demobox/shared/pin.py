"""The loose MT1 locating pin.

The plinth has a PEG_HOLE_D hole at each revision's MT1 (``Layout.pins``,
``"<rev>/MT1"``), down its full height to the floor (``socket_depth``); the
fitted revision's hole takes this printed pin, which stands from the floor
to PIN_PROUD above the PCB top, through the board's MT1 hole.  Built
standing on Z = 0, axis on Z, in its own frame: it is a loose part, and the
two holes it may go in are ``Layout.pins``.
"""

from __future__ import annotations

import cadquery as cq

from demobox.layout import PEG_DIA, Layout

#: Lead-in chamfer on the pin's top edge.
PIN_CHAMFER = 0.3


def socket_depth(lay: Layout) -> float:
    """How deep the plinth's MT1 holes are: its full height, to the floor."""
    return lay.plinth.z1 - lay.plinth.z0


def locating_pin(lay: Layout) -> cq.Workplane:
    """The pin: PEG_DIA across, from the bottom of its hole to the MT1
    pins' top (PIN_PROUD above the PCB top)."""
    tops = {p.z1 for k, p in lay.pins.items() if k.endswith("/MT1")}
    if len(tops) != 1:
        raise ValueError(f"MT1 pins at different heights {sorted(tops)}: one pin will not do")
    length = tops.pop() - (lay.plinth.z1 - socket_depth(lay))
    return (cq.Workplane("XY").circle(PEG_DIA / 2).extrude(length)
            .faces(">Z").edges().chamfer(PIN_CHAMFER))
