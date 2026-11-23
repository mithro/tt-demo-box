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
