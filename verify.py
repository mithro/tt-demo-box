#!/usr/bin/env python3
"""Prove the demo box fits, for both build routes.

Seven claims, each a function in ``demobox.checks``, run against
``layout(wall)`` for the printed and the laser route:

* every monitor fits the lid: its bezel window shows the whole picture and
  hides the panel's edges, its insert has material all round, the stack fits
  the pocket depth, and its cable leaves through a lid-wall opening the plug
  passes;
* every power bank fits the drawer with its packing, ports at the cable bay;
* every button can be reached: the banks' with the drawer out, the monitors'
  through the bezel with the lid open;
* both board revisions seat on the deck;
* the closed lid clears the tallest thing on the deck;
* the lid swings from closed to the stop, every degree, without meeting the
  base or anything on the deck;
* the cables route: drawer travel, slack loop, bend radii, VGA length.

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


def main() -> int:
    bad = tested = 0
    unconfirmed = checks.Unconfirmed()
    for route, wall in L.ROUTES.items():
        lay = L.layout(wall)
        o = lay.outer
        print(f"Demo box, {route} route: wall {wall} mm, base {o.size[0]:.2f} x "
              f"{o.size[1]:.2f} x {o.size[2]:.2f} mm\n")
        report = checks.Report()
        for proof in checks.PROOFS:
            proof(report, lay)
        _print(report)
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
