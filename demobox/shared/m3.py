"""M3 hardware the made parts are fastened with (bought parts, ISO sizes)."""

from __future__ import annotations

#: Clearance hole for an M3 shank.
CLEARANCE_D = 3.4
#: Socket / pan head: radius and height.
HEAD_R = 2.75
HEAD_H = 3.0
#: Nyloc nut height, and the thread to leave past it.
NYLOC_H = 4.0
THREAD_PAST = 1.0
#: Stock bolt lengths (mm).
LENGTHS = (6, 8, 10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60)


def stock_length(need: float) -> int:
    """The shortest stock M3 bolt at least ``need`` long."""
    for n in LENGTHS:
        if n >= need:
            return n
    raise ValueError(f"no stock M3 bolt of {need:.1f} mm")


#: A screw into a blind heat-set insert stops this far short of the hole's
#: floor, and engages at least MIN_ENGAGE of thread.
INSERT_SHORT = 0.5
MIN_ENGAGE = 3.0


def insert_screw(clamp: float, hole_depth: float) -> int:
    """The longest stock M3 screw through ``clamp`` mm of parts into a blind
    insert hole ``hole_depth`` deep that stops INSERT_SHORT short of its floor.
    ``stock_length`` rounds UP, which is right for a through bolt and wrong
    here: rounding up drives the screw into the hole's floor.  Raises if that
    screw would engage less than MIN_ENGAGE."""
    limit = clamp + hole_depth - INSERT_SHORT
    fits = [n for n in LENGTHS if n <= limit + 1e-9]
    if not fits or fits[-1] - clamp < MIN_ENGAGE:
        raise ValueError(f"no stock M3 screw through {clamp:.2f} mm engages "
                         f"{MIN_ENGAGE} mm of a {hole_depth:.2f} mm insert hole")
    return fits[-1]
