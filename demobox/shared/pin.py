"""The loose MT1 locating pin.

The MT1 boss (``Layout.mt1_boss``) has a PEG_DIA hole down to the deck at each
revision's MT1; the fitted revision's hole takes this printed pin, which
stands PEG_HEIGHT proud of the boss into the board's MT1 hole
(``Layout.pegs``).  Built standing on Z = 0, axis on Z, in its own frame: it is
a loose part, and the two holes it may go in are ``Layout.pegs``.
"""

from __future__ import annotations

import cadquery as cq

from demobox.layout import PEG_DIA, Layout

#: Lead-in chamfer on the pin's top edge.
PIN_CHAMFER = 0.3


def locating_pin(lay: Layout) -> cq.Workplane:
    """The pin: PEG_DIA across, from the deck to the pegs' top."""
    tops = {p.z1 for p in lay.pegs.values()}
    if len(tops) != 1:
        raise ValueError(f"MT1 pegs at different heights {sorted(tops)}: one pin will not do")
    length = tops.pop() - lay.mt1_boss.z0
    return (cq.Workplane("XY").circle(PEG_DIA / 2).extrude(length)
            .faces(">Z").edges().chamfer(PIN_CHAMFER))
