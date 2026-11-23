"""TinyVGA numbers must equal a fresh extraction from the fetched KiCad file (R1)."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

import demobox  # noqa: F401  (puts the submodule on sys.path)
from demobox._paths import ROOT
from demobox.parts import tinyvga, tinyvga_data

CLONE = ROOT / "tmp" / "src" / "tiny-vga"


def _extractor():
    spec = importlib.util.spec_from_file_location(
        "extract_tinyvga", ROOT / "scripts" / "extract_tinyvga.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def clone():
    if not CLONE.exists():
        pytest.fail("tmp/src/tiny-vga is missing: run make fetch")
    return CLONE


def test_tinyvga_from_kicad(clone):
    ex = _extractor()
    got = ex.extract(clone / "pcb" / "tiny-vga.kicad_pcb")
    assert got == tinyvga_data.EXTRACTED
    # the public parts are built from exactly those numbers
    x0, y0, x1, y1 = tinyvga_data.EXTRACTED["pcb"]
    assert tinyvga.TINYVGA.pcb.size[:2] == pytest.approx((x1 - x0, y1 - y0))
    dx0, dy0, dx1, dy1 = tinyvga_data.EXTRACTED["de15"]
    assert (tinyvga.TINYVGA.de15.x0, tinyvga.TINYVGA.de15.y0) == (dx0, dy0)


def test_pinned_commit_is_what_was_fetched(clone):
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()
    assert head == tinyvga_data.COMMIT, "tmp/src/tiny-vga differs from the pin: run make fetch"
    assert tinyvga_data.COMMIT in tinyvga_data.SOURCES[0].ref


def test_geometry_sanity():
    t = tinyvga.TINYVGA
    assert t.pcb.y1 == 0.0                       # host-side edge at y = 0
    assert t.de15.y0 < t.pcb.y0                  # DE-15 sticks out past the PCB's far edge
    assert t.confirmed is False
    straight, angled = t.plug_keepout(True), t.plug_keepout(False)
    assert straight.y0 < angled.y0 < t.de15.y0   # keepouts continue outward from the face
    assert straight.y1 == angled.y1 == t.de15.y0
    assert straight.size[1] - angled.size[1] == pytest.approx(20.0)


def test_reach_from_host_edge_is_socket_overhang_plus_pcb_to_face():
    from demobox.parts.board import board_spec
    for key in ("v3.2", "v3.3"):
        pmod = board_spec(key).pmods[2]
        expect = -pmod.body_y0 + (-tinyvga.TINYVGA.de15.y0)
        assert tinyvga.reach_from_host_edge(key) == pytest.approx(expect)
        assert 55 < expect < 65   # ~59.8 mm; photo estimate ~53 +/- 5
