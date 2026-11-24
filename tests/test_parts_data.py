"""Monitor, battery and cable data (task 3)."""

import pytest

import demobox  # noqa: F401  (puts the submodule on sys.path)
from tools.schema import Source

from demobox.parts.batteries import BATTERIES
from demobox.parts.cables import CABLES
from demobox.parts.monitors import MONITORS

ALLOWED_EXITS = {"left", "right", "top", "bottom", "pigtail", "board"}  # never "rear"


def approx(t, expected):
    return t == pytest.approx(expected)


def test_monitor_keys():
    assert set(MONITORS) == {"taobao-tim", "car-7-aliexpress", "kit-at070tn92"}


def test_car_7_aliexpress_panel():
    assert MONITORS["car-7-aliexpress"].panel == (173, 113, 20)


def test_kit_driver_board_size():
    d = MONITORS["kit-at070tn92"].driver
    assert approx(d.size[:2], (90.6, 65.7))
    assert MONITORS["kit-at070tn92"].kind == "kit"


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_active_is_7in_16x9_class(key):
    w, h = MONITORS[key].active
    assert 150 <= w <= 160 and 85 <= h <= 90


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_no_rear_facing_socket(key):
    assert MONITORS[key].connector_exit in ALLOWED_EXITS


@pytest.mark.parametrize("key", sorted(MONITORS))
def test_monitor_internal_consistency(key):
    m = MONITORS[key]
    assert m.sources and all(isinstance(s, Source) for s in m.sources)
    ox, oy = m.active_offset
    assert ox >= 0 and oy >= 0
    assert ox + m.active[0] <= m.panel[0] and oy + m.active[1] <= m.panel[1]
    if m.connector_exit in ("left", "right", "top", "bottom"):
        assert m.cable_edge == m.connector_exit
    if m.connector_exit == "pigtail":
        assert m.cable_edge in ("left", "right", "top", "bottom")
    if m.window is not None:
        assert m.kind == "cased"


def test_taobao_tim():
    m = MONITORS["taobao-tim"]
    assert m.kind == "cased"
    assert m.panel[:2] == (182, 118)
    assert m.panel[2] == 20.0            # depth placeholder
    assert m.window == (159, 86)
    assert m.connector_exit == "pigtail"
    assert m.cable_edge == "bottom"      # long edge on the button side
    assert m.power_in == "12V-boost"
    assert m.confirmed is False
    assert any("170" in (s.label + s.ref + s.note) for s in m.sources)
    assert any("calipers" in s.note for s in m.sources)
    assert m.button is not None and m.button[1] < m.panel[1] / 2  # bottom edge


def test_bare_kits_have_no_window():
    assert MONITORS["kit-at070tn92"].window is None


@pytest.mark.parametrize("key,size", [
    ("iniu-p512", (104, 70, 29)),
    ("ugreen-pb505", (116.22, 70.55, 30.03)),
    ("xiaomi-pb2020", (128, 73, 32)),
    ("anker-zolo-20k", (119.9, 73.4, 31.5)),
])
def test_battery_sizes(key, size):
    assert BATTERIES[key].size == size


def test_battery_keys_and_sources():
    assert set(BATTERIES) == {"iniu-p512", "ugreen-pb505", "xiaomi-pb2020", "anker-zolo-20k"}
    for b in BATTERIES.values():
        assert b.sources and all(isinstance(s, Source) for s in b.sources)
        assert b.port_face in ("end", "top", "side")
        if b.button is not None:
            assert b.button[0] in ("end", "top", "side", "bottom", "front", "back")


def test_cable_data():
    assert set(CABLES) == {"vga-slim", "vga-90-adapter", "usb-c-right-angle",
                           "usb-a-c", "usb-12v-boost", "bank-built-in", "monitor-pigtail"}
    for c in CABLES.values():
        assert c.sources and all(isinstance(s, Source) for s in c.sources)
        assert c.dia > 0 and c.min_bend_r > 0 and all(p > 0 for p in c.plug)
    assert CABLES["usb-12v-boost"].confirmed is False


def test_monitor_pigtail_cable():
    """Rulings R13, R17: the monitor's own cable, a placeholder until measured."""
    c = CABLES["monitor-pigtail"]
    assert (c.dia, c.min_bend_r) == (5.0, 15.0)
    assert c.confirmed is False
    assert any(s.label.startswith("Placeholder: Tim's monitor's own hard-wired cable")
               and "3 x dia" in s.note and "208 x 209" in s.note for s in c.sources)


def test_vga_adapter_orientation_is_a_placeholder():
    """R16a: the left/right-angle adapter is assumed, and says so."""
    c = CABLES["vga-90-adapter"]
    assert c.plug == (35.0, 17.0, 20.0) and c.confirmed is False
    assert any(s.label == "Placeholder: adapter orientation" and "left/right-angle" in s.note
               and "up/down" in s.note for s in c.sources)


def test_ugreen_ports_on_the_end():
    """R14: the survey's "all on top face" is read as the short top end."""
    b = BATTERIES["ugreen-pb505"]
    assert b.port_face == "end" and b.button[0] == "end"
    assert any("read as the short top end" in s.note for s in b.sources)
    assert b.confirmed is False


def test_design_monitor_has_pigtail_placeholders():
    m = MONITORS["taobao-tim"]
    assert m.pigtail_len == 300.0 and 0 < m.pigtail_exit_u < m.panel[0]
    assert any("pigtail" in s.label.lower() for s in m.sources) and not m.confirmed
    for k, other in MONITORS.items():
        if k != "taobao-tim":
            assert other.pigtail_len is None and other.pigtail_exit_u is None


def test_bank_cable_kinds():
    assert BATTERIES["iniu-p512"].cable == "socket"
    assert {k for k, b in BATTERIES.items() if b.cable == "built-in"} == {
        "ugreen-pb505", "xiaomi-pb2020", "anker-zolo-20k"}


def test_bank_built_in_cable_data():
    c = CABLES["bank-built-in"]
    assert (c.dia, c.min_bend_r) == (4.0, 20.0)
    assert c.plug == (20.0, 9.0, 8.5) and c.confirmed is False
