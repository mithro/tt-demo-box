"""Axis-aligned geometry primitives shared by every part module.

Frames: a ``Box`` or ``Cyl`` carries no frame of its own; the module that
builds one states the frame in its docstring (board frame for
``demobox.parts.board``, the TinyVGA plug frame for ``demobox.parts.tinyvga``,
the base frame for the enclosure).  Only boxes in the same frame may be
compared with ``box_gap`` / ``overlaps``.  All lengths are millimetres.
"""

from __future__ import annotations

from dataclasses import dataclass, replace


class BedOverflow(Exception):
    """A part does not fit its machine bed (R5).

    The message must name the part and its size, e.g.
    ``BedOverflow("lid_frame 230.0 x 120.0 mm does not fit the 220 x 220 mm print bed")``.
    Printed-part and laser exports both raise this.
    """


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    z0: float
    x1: float
    y1: float
    z1: float
    what: str = ""

    def __post_init__(self) -> None:
        if self.x1 < self.x0 or self.y1 < self.y0 or self.z1 < self.z0:
            raise ValueError(f"Box {self.what!r} has negative extent: {self}")

    @property
    def size(self) -> tuple[float, float, float]:
        return (self.x1 - self.x0, self.y1 - self.y0, self.z1 - self.z0)

    def moved(self, dx: float, dy: float, dz: float) -> "Box":
        return replace(self, x0=self.x0 + dx, x1=self.x1 + dx,
                       y0=self.y0 + dy, y1=self.y1 + dy,
                       z0=self.z0 + dz, z1=self.z1 + dz)

    def union(self, other: "Box") -> "Box":
        return Box(min(self.x0, other.x0), min(self.y0, other.y0), min(self.z0, other.z0),
                   max(self.x1, other.x1), max(self.y1, other.y1), max(self.z1, other.z1),
                   f"{self.what}+{other.what}")


@dataclass(frozen=True)
class Cyl:
    """A cylinder with its axis along Z."""

    cx: float
    cy: float
    z0: float
    z1: float
    r: float
    what: str = ""


def box_gap(a: Box, b: Box) -> float:
    """Clearance between two boxes: positive = gap, 0 = touching, negative =
    overlap depth (the smallest translation that would separate them)."""
    gaps = [max(b.x0 - a.x1, a.x0 - b.x1),
            max(b.y0 - a.y1, a.y0 - b.y1),
            max(b.z0 - a.z1, a.z0 - b.z1)]
    positive = [g for g in gaps if g > 0]
    if positive:
        # Separated: Euclidean distance between the boxes.
        return sum(g * g for g in positive) ** 0.5
    return max(gaps)  # all <= 0: the shallowest axis is the overlap depth


def overlaps(a: Box, b: Box, tol: float = 0.0) -> bool:
    """True when the boxes interpenetrate by more than ``tol``."""
    return box_gap(a, b) < -tol
