"""The fit proofs: verify.py passes on the design kit and each proof bites."""

import math
from dataclasses import replace

import pytest
from shapely.geometry import box as sbox

from demobox import checks as C
from demobox import layout as L
from demobox.layout import Layout
from demobox.parts.batteries import BATTERIES
from demobox.parts.monitors import MONITORS

PROOF_NAMES = ("kit_fits", "boards_seat", "bank_lifts_out", "button_reachable",
               "lid_closed_clears", "hinge_sweep", "cables_route", "lid_catch", "size_budget")


@pytest.fixture(params=sorted(L.ROUTES.items()), ids=lambda r: r[0])
def lay(request):
    return L.layout(request.param[1])


def _failed(report: C.Report) -> list[str]:
    return [f"{what}: {detail}" for ok, what, detail in report.results if not ok]


def _run(proof, lay) -> C.Report:
    r = C.Report()
    proof(r, lay)
    return r


def test_proofs_are_the_nine_named():
    assert tuple(p.__name__ for p in C.PROOFS) == PROOF_NAMES


@pytest.mark.parametrize("proof", C.PROOFS, ids=lambda p: p.__name__)
def test_all_proofs_pass(proof, lay):
    """Both routes, the design kit."""
    r = _run(proof, lay)
    assert r.results, "a proof must record at least one check"
    assert r.failures == 0, _failed(r)


def test_main_prints_both_routes_and_unconfirmed(capsys):
    import verify
    verify.main()
    out = capsys.readouterr().out
    for route in L.ROUTES:
        assert route in out
    assert "UNCONFIRMED" in out
    for name in ("TAPE_T", "TALLEST_COMPONENT", "USB_C_AXIS_ABOVE_PCB", "vga-slim",
                 L.DESIGN_MONITOR, L.DESIGN_BANK):
        assert name in out, name


def test_verify_docstring_lists_exactly_the_proofs():
    import verify
    bullets = [line for line in verify.__doc__.splitlines() if line.startswith("* ")]
    assert len(bullets) == len(C.PROOFS)
    for p, line in zip(C.PROOFS, bullets):
        assert f"``{p.__name__}``" in line, (p.__name__, line)


def test_report_counts_failures_and_keeps_unconfirmed_apart():
    r = C.Report()
    r.check(True, "a", "fine")
    r.check(False, "b", "broken")
    r.unconfirmed("c", "placeholder")
    r.unconfirmed("c", "placeholder")      # recorded once
    assert r.failures == 1
    assert list(r.unconfirmed) == [("c", "placeholder")]


def test_unconfirmed_listed(lay):
    r = C.Report()
    for proof in C.PROOFS:
        proof(r, lay)
    names = " ".join(what for what, _ in r.unconfirmed)
    for name in ("TALLEST_COMPONENT", "USB_C_AXIS_ABOVE_PCB", "TINYVGA_Z_OFFSET", "TAPE_T",
                 "vga-slim", L.DESIGN_MONITOR, L.DESIGN_BANK):
        assert name in names, name


# --- each proof can fail ---------------------------------------------------------

def _wider_monitor(lay, mp):
    m = MONITORS[L.DESIGN_MONITOR]
    mp.setitem(MONITORS, m.key, replace(m, panel=(lay.monitor_space.size[0] + 1.0,) + m.panel[1:]))
    return lay


def _pins_moved(lay, mp):
    return replace(lay, pins={k: replace(p, cx=p.cx + 1.0) for k, p in lay.pins.items()})


def _bay_under_the_open_lid(lay, mp):
    # the bay runs 10 mm further back, under the lid standing at 100 degrees
    return replace(lay, bank_bay=replace(lay.bank_bay, y1=lay.bank_bay.y1 + 10.0))


def _short_port_room(lay, mp):
    p = lay.port_room
    return replace(lay, port_room=replace(p, x1=p.x0 + 10.0))


def _shallow_lid(lay, mp):
    return replace(lay, lid_outer=replace(lay.lid_outer, z1=lay.lid_outer.z1 - 3.0))


def _lid_enters_base(lay, mp):
    # the lid 6 mm further back along itself: a 10 mm strip behind the axis
    # swings down through the base as it opens
    return replace(lay, lid_outer=lay.lid_outer.moved(0.0, 6.0, 0.0))


def _short_pigtail(lay, mp):
    m = MONITORS[L.DESIGN_MONITOR]
    mp.setitem(MONITORS, m.key, replace(m, pigtail_len=100.0))
    return lay


def _magnet_moved(lay, mp):
    c0 = lay.lid_catch[0]
    return replace(lay, lid_catch=(replace(c0, z0=c0.z0 - 2.0, z1=c0.z1 - 2.0),)
                   + lay.lid_catch[1:])


def _wider_box(lay, mp):
    return replace(lay, outer=replace(lay.outer, x1=lay.outer.x1 + 5.0))


#: (proof, what every new failure must name, mutation)
MUTATIONS = [
    ("kit_fits", L.DESIGN_MONITOR, _wider_monitor),
    ("boards_seat", "pin", _pins_moved),
    ("bank_lifts_out", "bank bay", _bay_under_the_open_lid),
    ("button_reachable", "port room", _short_port_room),
    ("lid_closed_clears", "monitor face", _shallow_lid),
    ("hinge_sweep", "base", _lid_enters_base),
    ("cables_route", "pigtail", _short_pigtail),
    ("lid_catch", "lid catch 1", _magnet_moved),
    ("size_budget", "width", _wider_box),
]


def _failures_by_proof(lay) -> dict[str, set[str]]:
    return {p.__name__: set(_failed(_run(p, lay))) for p in C.PROOFS}


@pytest.mark.parametrize("name,names,mutate", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_each_proof_can_fail(name, names, mutate, lay, monkeypatch):
    """Exactly the named proof gains failures, and they name the offending part.
    Compared with the unmutated layout, so a proof already failing on the real
    data neither hides nor fakes a mutation's effect."""
    before = _failures_by_proof(lay)
    after = _failures_by_proof(mutate(lay, monkeypatch))
    new = {p: after[p] - before[p] for p in after}
    assert new[name], f"{name} did not fail"
    assert all(names in f for f in new[name]), new[name]
    others = {p: f for p, f in new.items() if p != name and f}
    assert not others, others


def test_mutations_cover_every_proof():
    assert sorted(m[0] for m in MUTATIONS) == sorted(PROOF_NAMES)


def test_deeper_monitor_still_clears(monkeypatch):
    """Review Focus 2: a 25 mm deep monitor regenerates a deeper lid that passes."""
    m = MONITORS[L.DESIGN_MONITOR]
    monkeypatch.setitem(MONITORS, m.key, replace(m, panel=m.panel[:2] + (25.0,)))
    failed = {}
    for route, wall in L.ROUTES.items():
        lay = L.layout(wall)
        assert lay.monitor_space.size[2] == pytest.approx(25.0)
        for proof in C.PROOFS:
            f = _failed(_run(proof, lay))
            if f:
                failed[(route, proof.__name__)] = f
    assert not failed, failed


# --- fit reports -----------------------------------------------------------------

def test_fit_reports_list_monitors_and_banks(lay, capsys):
    mons = C.monitor_fit_report(lay)
    banks = C.bank_fit_report(lay)
    assert [k for k, _, _ in mons] == list(MONITORS)
    assert [k for k, _, _ in banks] == list(BATTERIES)
    fits = {k: ok for k, ok, _ in mons + banks}
    assert fits[L.DESIGN_MONITOR] and fits[L.DESIGN_BANK]
    assert fits["kit-at070tn92"]                    # 165 x 100 x 5.7: smaller every way
    assert not fits["anker-zolo-20k"]               # 73.4 wide in a bay for 73
    import verify
    verify.main()
    out = capsys.readouterr().out
    for k in list(MONITORS) + list(BATTERIES):
        lines = [ln for ln in out.splitlines()
                 if k in ln and ln.lstrip().startswith(("fits", "does not fit"))]
        assert lines, k
        for ln in lines:
            assert ("does not fit" in ln) == (not fits[k]), ln


def test_fit_reports_never_fail_the_run(lay, monkeypatch):
    base = MONITORS["kit-at070tn92"]
    monkeypatch.setitem(MONITORS, "huge", replace(base, key="huge", panel=(400.0, 300.0, 50.0)))
    r = C.Report()
    for proof in C.PROOFS:
        proof(r, lay)
    assert not any("huge" in what for _, what, _ in r.results)
    assert not dict((k, ok) for k, ok, _ in C.monitor_fit_report(lay))["huge"]


# --- the hinge sweep ---------------------------------------------------------------

def test_hinge_sweep_samples_every_degree(monkeypatch, lay):
    seen = []
    real = Layout.lid_profile_yz

    def spy(self, angle_deg):
        seen.append(angle_deg)
        return real(self, angle_deg)

    monkeypatch.setattr(Layout, "lid_profile_yz", spy)
    _run(C.hinge_sweep, lay)
    assert sorted(set(seen)) == [float(a) for a in range(0, 101)]
    assert C.sweep_angles()[-1] == L.LID_OPEN_DEG


def test_closed_lid_touches_but_is_no_collision(lay):
    o = lay.outer
    base = sbox(o.y0, o.z0, o.y1, o.z1)
    closed = lay.lid_profile_yz(0.0)
    assert closed.intersects(base)                     # it sits on the base
    assert closed.intersection(base).area <= C.AREA_TOL


# --- the pigtail path ---------------------------------------------------------------

def test_pigtail_path_runs_exit_notch_plug(lay):
    hy, hz = lay.hinge_axis
    n = lay.hinge_notch
    v = lay.board_keepouts["v3.2/tinyvga"]
    for a in (0.0, 50.0, L.LID_OPEN_DEG):
        path = C.pigtail_path(lay, a)
        assert all(len(p) == 3 for p in path)
        assert any(math.isclose(y, hy) and math.isclose(z, hz) and n.x0 < x < n.x1
                   for x, y, z in path), "through the hinge axis, inside the notch"
        x, y, z = path[-1]                      # the TinyVGA's DE-15 face
        assert v.x0 <= x <= v.x1 and v.y0 <= y <= v.y1 and v.z0 <= z <= v.z1
    x0, y0, _ = C.pigtail_path(lay, 0.0)[0]
    ms = lay.monitor_space
    assert ms.x0 < x0 < ms.x1
    assert y0 == pytest.approx(ms.y1 - L.SLACK + hy)        # the panel's cable edge


def test_pigtail_length_same_at_every_angle(lay):
    lengths = {round(C.path_length(C.pigtail_path(lay, a)), 6) for a in C.sweep_angles()}
    assert len(lengths) == 1


def test_bend_radius_of_a_right_angle_corner():
    # a 90 degree corner with 10 mm legs takes a 10 mm fillet, no more
    pts = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0)]
    assert C.max_bend_r(pts) == pytest.approx(10.0)
    # two corners share the leg between them
    pts = [(0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (10.0, 10.0, 0.0), (20.0, 10.0, 0.0)]
    assert C.max_bend_r(pts) == pytest.approx(5.0)
    assert C.max_bend_r([(0.0, 0.0, 0.0), (5.0, 0.0, 0.0), (9.0, 0.0, 0.0)]) == math.inf


# --- the lid catch ------------------------------------------------------------------

def test_lid_catch_fails_over_the_board(lay):
    env = lay.board_keepouts["v3.2/envelope"]
    over = tuple(replace(c, cx=(env.x0 + env.x1) / 2) for c in lay.lid_catch)
    assert _failed(_run(C.lid_catch, replace(lay, lid_catch=over)))


# --- the closed lid ---------------------------------------------------------------

def test_board_lift_bounded_only_under_the_panel(lay):
    """The lift bound holds because the tallest keep-out is under the panel;
    move the panel off it in XY and the proof fails."""
    away = replace(lay, monitor_space=lay.monitor_space.moved(500.0, 0.0, 0.0))
    failed = _failed(_run(C.lid_closed_clears, away))
    assert any("under the monitor" in f for f in failed), failed
