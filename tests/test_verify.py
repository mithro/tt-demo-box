"""The fit proofs: verify.py passes on the real data and each proof bites."""

from dataclasses import replace

import pytest
from shapely.geometry import box as sbox

from demobox import checks as C
from demobox import layout as L
from demobox.geom import Box
from demobox.layout import Layout
from demobox.parts import board as board_mod
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS

PROOFS = (C.monitors_fit, C.batteries_fit, C.buttons_reachable, C.boards_seat,
          C.lid_closed_clears, C.hinge_sweep, C.cables_route)


@pytest.fixture(params=sorted(L.ROUTES.items()), ids=lambda r: r[0])
def lay(request):
    return L.layout(request.param[1])


def _failed(report: C.Report) -> list[str]:
    return [f"{what}: {detail}" for ok, what, detail in report.results if not ok]


def _run(proof, lay) -> C.Report:
    r = C.Report()
    proof(r, lay)
    return r


def test_main_returns_zero_on_real_data(capsys):
    import verify
    assert verify.main() == 0
    out = capsys.readouterr().out
    for route in L.ROUTES:
        assert route in out
    assert "UNCONFIRMED" in out and "PASS" in out


def test_report_counts_failures_and_keeps_unconfirmed_apart():
    r = C.Report()
    r.check(True, "a", "fine")
    r.check(False, "b", "broken")
    r.unconfirmed("c", "placeholder")
    r.unconfirmed("c", "placeholder")      # recorded once
    assert r.failures == 1
    assert list(r.unconfirmed) == [("c", "placeholder")]


@pytest.mark.parametrize("proof", PROOFS, ids=lambda p: p.__name__)
def test_every_proof_passes_on_real_data(proof, lay):
    r = _run(proof, lay)
    assert r.results, "a proof must record at least one check"
    assert r.failures == 0, _failed(r)


def test_unconfirmed_data_reported_without_failing(lay):
    r = C.Report()
    for proof in PROOFS:
        proof(r, lay)
    assert r.failures == 0
    names = " ".join(what for what, _ in r.unconfirmed)
    for key in list(MONITORS) + list(BATTERIES):
        assert key in names
    for name in ("TALLEST_COMPONENT", "USB_C_AXIS_ABOVE_PCB", "TINYVGA_Z_OFFSET", "vga-slim"):
        assert name in names


# --- monitors ------------------------------------------------------------------

def test_monitor_window_rule():
    for m in MONITORS.values():
        w, h, x, y = C.monitor_window(m)
        ax, ay = m.active_offset
        aw, ah = m.active
        assert x <= ax and y <= ay and x + w >= ax + aw and y + h >= ay + ah, m.key
        W, H, _ = m.panel
        assert min(x, y, W - x - w, H - y - h) >= C.WINDOW_INSET - 1e-9, m.key
        if m.window is not None:
            assert w >= m.window[0] and h >= m.window[1], m.key


def test_small_panel_fails_naming_it(monkeypatch, lay):
    base = MONITORS["kit-at070tn92"]
    monkeypatch.setitem(MONITORS, "tiny-140", replace(base, key="tiny-140",
                                                       panel=(140.0, 100.0, 5.7)))
    failed = _failed(_run(C.monitors_fit, lay))
    assert failed and all("tiny-140" in f for f in failed), failed


def test_connector_opening_fits_the_plug(lay):
    plug = C.VGA_PLUG
    for m in MONITORS.values():
        o = C.connector_opening(m, lay)
        across = sorted(o.size)[1:]          # the two sizes across the wall
        assert min(across) >= min(plug[1:]) + 2 * L.FIT - 1e-9, m.key
        assert max(across) >= max(plug[1:]) + 2 * L.FIT - 1e-9, m.key


def test_too_shallow_lid_fails_the_side_opening(lay):
    shallow = replace(lay, lid_pocket=replace(lay.lid_pocket, z1=15.0))
    failed = _failed(_run(C.monitors_fit, shallow))
    assert any("car-7-aliexpress" in f and "opening" in f for f in failed), failed


# --- batteries and buttons -----------------------------------------------------

def test_long_battery_fails(monkeypatch, lay):
    base = BATTERIES["iniu-p512"]
    monkeypatch.setitem(BATTERIES, "huge", replace(base, key="huge", size=(170.0, 70.0, 29.0)))
    failed = _failed(_run(C.batteries_fit, lay))
    assert failed and all("huge" in f for f in failed), failed


def test_bank_buttons_need_the_drawer_open(lay):
    r = _run(C.buttons_reachable, lay)
    notes = {what: detail for what, detail in r.unconfirmed}
    for b in BATTERIES.values():
        if b.button is not None:
            assert any(b.key in w and "press with drawer open" in d for w, d in notes.items()), b.key


def test_bank_button_covered_with_drawer_out_fails(monkeypatch, lay):
    base = BATTERIES["iniu-p512"]
    monkeypatch.setitem(BATTERIES, "side-btn", replace(base, key="side-btn",
                                                       button=("side", 50.0, 15.0)))
    failed = _failed(_run(C.buttons_reachable, lay))
    assert failed and all("side-btn" in f for f in failed), failed
    short = replace(lay, drawer_travel=10.0)
    failed = _failed(_run(C.buttons_reachable, short))
    assert {b.key for b in BATTERIES.values() if b.button} <= {
        k for k in BATTERIES if any(k in f for f in failed)}


def test_monitor_button_against_the_base_fails(monkeypatch, lay):
    base = MONITORS["taobao-tim"]
    monkeypatch.setitem(MONITORS, "low-btn", replace(base, key="low-btn", button=(60.0, 0.5)))
    # the hinge gutter keeps real panels well off the hinge; put the pocket
    # back against the hinge-end wall so a button at the very edge meets the base
    p = lay.lid_pocket
    tight = replace(lay, lid_pocket=p.moved(0.0, -lay.wall - p.y1, 0.0))
    failed = _failed(_run(C.buttons_reachable, tight))
    assert failed and all("low-btn" in f for f in failed), failed


# --- boards and closed lid -------------------------------------------------------

def test_tall_component_fails_closed_lid(monkeypatch, lay):
    monkeypatch.setattr(board_mod, "TALLEST_COMPONENT", 60.0)
    failed = _failed(_run(C.lid_closed_clears, lay))
    assert failed and all("tallest component" in f for f in failed), failed


def test_board_off_its_standoffs_fails(lay):
    lifted = replace(lay, board_origin=(lay.board_origin[0], lay.board_origin[1],
                                        lay.board_origin[2] + 1.0))
    assert _run(C.boards_seat, lifted).failures > 0


# --- hinge sweep -----------------------------------------------------------------

def test_hinge_sweep_samples_every_degree(monkeypatch, lay):
    seen = []
    real = Layout.lid_profile_yz

    def spy(self, angle_deg):
        seen.append(angle_deg)
        return real(self, angle_deg)

    monkeypatch.setattr(Layout, "lid_profile_yz", spy)
    r = _run(C.hinge_sweep, lay)
    assert r.failures == 0
    assert sorted(set(seen)) == [float(a) for a in range(0, 101)]
    assert len(set(seen)) == 101


def test_closed_lid_touches_but_is_no_collision(lay):
    o = lay.outer
    base = sbox(o.y0, o.z0, o.y1, o.z1)
    closed = lay.lid_profile_yz(0.0)
    assert closed.intersects(base)                     # it sits on the base
    assert closed.intersection(base).area <= C.AREA_TOL
    assert _run(C.hinge_sweep, lay).failures == 0


def test_hinge_sweep_fails_on_overlap(lay):
    hy, hz = lay.hinge_axis
    # behind the hinge, high up: only the opening lid passes through it
    post = Box(lay.outer.x0, hy + 5.0, hz + 50.0, lay.outer.x1, hy + 10.0, hz + 60.0, "post")
    hit = replace(lay, board_keepouts={**lay.board_keepouts, "post": post})
    failed = _failed(_run(C.hinge_sweep, hit))
    assert failed and any("post" in f for f in failed), failed
    # the same post off to one side, clear of the lid in X, is no collision
    aside = replace(post, x0=lay.outer.x1 + 1.0, x1=lay.outer.x1 + 5.0)
    clear = replace(lay, board_keepouts={**lay.board_keepouts, "post": aside})
    assert _run(C.hinge_sweep, clear).failures == 0


# --- cables ------------------------------------------------------------------------

def test_short_drawer_travel_fails(lay):
    short = replace(lay, drawer_travel=lay.bay.x0 + 50.0)
    failed = _failed(_run(C.cables_route, short))
    assert any("drawer travel" in f for f in failed), failed


def test_slack_loop_too_short_fails(lay):
    far = replace(lay, drawer_travel=500.0)
    failed = _failed(_run(C.cables_route, far))
    assert any("slack loop" in f for f in failed), failed


def test_vga_too_long_fails(monkeypatch, lay):
    monkeypatch.setattr(C, "VGA_MAX_LEN", 100.0)
    failed = _failed(_run(C.cables_route, lay))
    assert any("VGA path" in f for f in failed), failed


def test_tight_channel_fails_bend(lay):
    c = lay.hinge_cable_channel
    tight = replace(lay, hinge_cable_channel=replace(c, y0=c.y1 - 10.0))
    failed = _failed(_run(C.cables_route, tight))
    assert any("bend" in f for f in failed), failed


# --- R13: in-lid cable route --------------------------------------------------------

def test_every_monitor_has_an_in_lid_route(lay):
    r = _run(C.cables_route, lay)
    for m in MONITORS.values():
        mine = [(ok, w) for ok, w, _ in r.results if m.key in w and "in-lid" in w]
        assert mine and all(ok for ok, _ in mine), (m.key, mine)


def test_too_narrow_side_gutter_fails_naming_the_monitor(lay):
    g = lay.lid_cable_gutters["right"]
    narrow = replace(lay, lid_cable_gutters={**lay.lid_cable_gutters,
                                             "right": replace(g, x1=g.x0 + 5.0)})
    failed = _failed(_run(C.cables_route, narrow))
    assert failed and any("car-7-aliexpress" in f and "in-lid" in f for f in failed), failed
    assert not any("taobao-tim" in f for f in failed), failed


def test_too_shallow_hinge_gutter_fails(lay):
    g = lay.lid_cable_gutters["hinge"]
    shallow = replace(lay, lid_cable_gutters={**lay.lid_cable_gutters,
                                              "hinge": replace(g, y0=g.y1 - 5.0)})
    failed = _failed(_run(C.cables_route, shallow))
    assert any("taobao-tim" in f and "in-lid" in f for f in failed), failed


def test_top_exit_has_no_route(monkeypatch, lay):
    base = MONITORS["car-7-aliexpress"]
    monkeypatch.setitem(MONITORS, "top-exit", replace(base, key="top-exit",
                                                       connector_exit="top", cable_edge="top"))
    failed = _failed(_run(C.cables_route, lay))
    assert any("top-exit" in f and "in-lid" in f for f in failed), failed
