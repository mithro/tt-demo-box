"""Finger joints for the laser-cut panels (glued; no screws, spec Decision 9).

Edge-local coordinates: ``x`` runs along the edge from 0 to ``length``;
``y`` is the depth into the panel from its nominal outer edge (y = 0), so a
finger joint's slots have their floors at y = ``t`` (the mating panel's
thickness).

Fingers
-------
``finger_count(length, t)``: the odd number nearest ``length / (3 t)``, at
least 3, so fingers are about 3 t wide.  The edge is cut into that many equal
segments; the *male* side owns the even ones (both ends), the *female* side
the odd ones, so the two patterns are complementary.

Kerf is added to every cut edge: the cut path is the nominal outline grown
kerf / 2 outward (holes shrink by kerf / 2), which the beam takes off again.
On a finger edge that makes every finger kerf / 2 wider each side and its tip
kerf / 2 proud, and every slot kerf / 2 narrower each side and kerf / 2
shallower: ``finger_edge`` is that compensated profile.  The panels build
their outlines nominal and grow them by kerf / 2 as a whole
(``Panel.cut_shape``), which gives exactly these profiles.
"""

from __future__ import annotations

import math


def finger_count(length: float, t: float) -> int:
    """The odd number nearest ``length / (3 t)`` (halves round up), at least 3."""
    x = length / (3.0 * t)
    n = 2 * math.floor((x - 1.0) / 2.0 + 0.5) + 1
    return max(3, n)


def finger_segments(length: float, t: float, male: bool) -> list[tuple[float, float]]:
    """The (x0, x1) intervals of the edge this side owns (nominal, no kerf)."""
    n = finger_count(length, t)
    w = length / n
    first = 0 if male else 1
    return [(i * w, length if i == n - 1 else (i + 1) * w) for i in range(first, n, 2)]


def finger_edge(length: float, t: float, kerf: float, male: bool) -> list[tuple[float, float]]:
    """The kerf-compensated profile of a finger edge, from x = -kerf/2 to
    length + kerf/2: fingers at y = -kerf/2, slot floors at y = t - kerf/2,
    each finger kerf/2 wider each side."""
    k = kerf / 2.0
    n = finger_count(length, t)
    w = length / n

    def owned(i: int) -> bool:
        return (i % 2 == 0) == male

    def y(i: int) -> float:
        return -k if owned(i) else t - k

    pts = [(-k, y(0))]
    for i in range(n - 1):
        b = (i + 1) * w
        x = b + k if owned(i) else b - k
        pts += [(x, y(i)), (x, y(i + 1))]
    pts.append((length + k, y(n - 1)))
    return pts
