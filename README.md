# tt-demo-box

A portable, zero-setup Tiny Tapeout VGA demo station: a small clamshell box with a 7" VGA
monitor in the lid, a Tiny Tapeout ETR dev board (with the TinyVGA Pmod) exposed on the deck,
and a power bank in a slide-out drawer underneath that comes out for airport security.

Two build routes from one design: 3D printed, and laser-cut 3 mm plywood.

The design is in [`docs/superpowers/specs/2026-11-23-tt-demo-box-design.md`](docs/superpowers/specs/2026-11-23-tt-demo-box-design.md).

Licensed under the Apache License 2.0.

## Building

Clone with submodules (`git clone --recurse-submodules`, or `git submodule update --init`).
Everything runs through `uv` and `make`; there is no `pyproject.toml`.

- `make test`: run the pytest suite
- `make tools`: check that `inkscape` and `blender` are installed
  (`sudo apt install inkscape blender`)
- `make verify`, `make outputs`, `make check`: filled in by later tasks

Board dimensions come from the `vendor/fpgas.online-mechanical` submodule, pinned at commit
`2273d7d40043b781003859c7cd4e67626b48c019`.
