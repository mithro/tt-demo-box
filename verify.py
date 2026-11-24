#!/usr/bin/env python3
"""Prove the demo box fits its kit, for both build routes.

The claims, each a function in ``demobox.checks``, run against
``layout(wall)`` for the printed and the laser route:

* ``kit_fits``: the design monitor fits the lid's monitor space and the
  design bank the bank bay, each with SLACK;
* ``boards_seat``: both board revisions sit on the plinth inside the walls,
  each pin in its PCB hole and its plinth hole, nothing overlapping;
* ``bank_lifts_out``: with the lid at its stop nothing is over the bank, as
  packed in its bay, above the rim, so it lifts straight out;
* ``button_reachable``: the bank's button faces the port room, which takes
  a fingertip;
* ``lid_closed_clears``: closed, the monitor face clears everything in the
  base, and the board can't lift off its pins;
* ``hinge_sweep``: every degree from closed to its open angle, the lid
  misses everything in the base: whole where the knuckles go (``knuckle_x``),
  cut back to the hinge relief elsewhere;
* ``cables_route``: the monitor's pigtail reaches the VGA plug's stiff run
  (in the bank row's back corner) through the hinge notch, within its length
  and bend radius at every angle, and the bank's USB cable reaches J1;
* ``lid_catch``: the catch magnets face each other when shut, their blocks
  clear of the board and the monitor;
* ``size_budget``: the box is no bigger than its contents + SLACK + walls.

Then, for information only (never a failure): which listed monitors would fit
the lid, and which listed banks the bank bay.

Figures that are placeholders are listed as UNCONFIRMED at the end: printed,
not trusted, and not failures on their own.

Run: make verify
"""

from __future__ import annotations

import sys

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox import checks
from demobox import layout as L


def _print(report: checks.Report) -> None:
    for ok, what, detail in report.results:
        print(f"   {'ok  ' if ok else 'FAIL'} {what}\n        {detail}")
    print()


def _print_fits(title: str, rows) -> None:
    print(f"   {title} (information, not a check):")
    for key, ok, detail in rows:
        print(f"   {'fits        ' if ok else 'does not fit'}  {key}: {detail}")
    print()


def main() -> int:
    bad = tested = 0
    unconfirmed = checks.Unconfirmed()
    for route, wall in L.ROUTES.items():
        lay = L.layout(wall)
        o = lay.outer
        print(f"Demo box, {route} route: wall {wall} mm, base {o.size[0]:.2f} x "
              f"{o.size[1]:.2f} x {o.size[2]:.2f} mm, kit {L.DESIGN_MONITOR} + "
              f"{L.DESIGN_BANK}\n")
        report = checks.Report()
        for proof in checks.PROOFS:
            proof(report, lay)
        _print(report)
        _print_fits("Listed monitors in this lid", checks.monitor_fit_report(lay))
        _print_fits("Listed banks in this bank bay", checks.bank_fit_report(lay))
        bad += report.failures
        tested += len(report.results)
        for item in report.unconfirmed:
            unconfirmed(*item)

    print(f"UNCONFIRMED ({len(unconfirmed)} placeholder figures; measure and confirm)\n")
    for what, detail in unconfirmed:
        print(f"   --   {what}\n        {detail}")
    print()
    print(f"PASS: {tested} checks over {len(L.ROUTES)} routes, {len(unconfirmed)} UNCONFIRMED"
          if not bad else f"FAIL: {bad} of {tested} checks")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
