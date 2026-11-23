"""Finger joints and M3 T-slots for the laser-cut panels.

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

T-slot
------
An M3 x TSLOT_SCREW screw passes through a clearance hole in one panel (its
finger, at the middle of the finger) into the other panel's edge, where the
T-slot is cut: a SLOT_W shank slot TSLOT_SCREW - t + SLOT_PAST deep, crossed
by a square-nut pocket (``nut_pocket``) whose far face leaves THREAD_PAST of
screw beyond the nut.  The nut is pushed into the pocket from the panel's face
and stands (NUT_W - t) / 2 proud of each face; the assemblies model it as a
``hw:nut`` keep-out so where it stands proud is clash-checked.
"""

from __future__ import annotations

import math

from demobox.shared import m3

#: M3 screw length through a T-slot, and the shank slot's width.
TSLOT_SCREW = 12
SLOT_W = m3.CLEARANCE_D
#: Shank slot beyond the screw's tip.
SLOT_PAST = 0.5
#: Thread left beyond the nut.
THREAD_PAST = m3.THREAD_PAST
#: ISO M3 square nut (DIN 562): width across flats, thickness; pocket fit per side.
NUT_W = 5.5
NUT_T = 1.8
NUT_FIT = 0.1


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


def nut_pocket(t: float) -> tuple[float, float]:
    """(y0, y1) of the square-nut pocket along the screw, from the edge the
    screw enters, for a screw through a ``t`` thick panel."""
    y1 = TSLOT_SCREW - t - THREAD_PAST
    return y1 - NUT_T - 2 * NUT_FIT, y1


def tslot(at: float, t: float) -> list[tuple[float, float]]:
    """The T-slot cut-out in an edge (edge-local, open at y = 0), centred on
    ``at``, for an M3 x TSLOT_SCREW screw through a ``t`` thick mating panel:
    the shank slot and the nut pocket across it (counter-clockwise)."""
    s, n = SLOT_W / 2, NUT_W / 2 + NUT_FIT
    y0, y1 = nut_pocket(t)
    depth = TSLOT_SCREW - t + SLOT_PAST
    if y0 <= 0 or depth <= y1:
        raise ValueError(f"a {t} mm panel leaves no room for the T-slot's nut")
    return [(at - s, 0.0), (at + s, 0.0), (at + s, y0), (at + n, y0), (at + n, y1),
            (at + s, y1), (at + s, depth), (at - s, depth), (at - s, y1), (at - n, y1),
            (at - n, y0), (at - s, y0)]
