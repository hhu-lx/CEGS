import pandapower as pp
import pytest

from src.infrastructure.continuation_power_flow import run_continuation_power_flow


def test_reaching_search_limit_is_not_reported_as_power_flow_failure():
    network = pp.create_empty_network()
    bus = pp.create_bus(network, vn_kv=110)
    pp.create_ext_grid(network, bus)
    pp.create_load(network, bus, p_mw=10, q_mvar=1)

    result = run_continuation_power_flow(network, step=0.05, max_steps=2)

    assert result["converged"] is True
    assert result["critical_point_found"] is False
    assert result["search_limit_reached"] is True
    assert result["voltage_margin_pct"] == pytest.approx(10)


def test_failed_initial_power_flow_is_reported_as_not_converged(monkeypatch):
    network = pp.create_empty_network()
    bus = pp.create_bus(network, vn_kv=110)
    pp.create_ext_grid(network, bus)
    pp.create_load(network, bus, p_mw=10, q_mvar=1)

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic power-flow failure")

    monkeypatch.setattr(pp, "runpp", fail)
    result = run_continuation_power_flow(network)

    assert result["converged"] is False
    assert result["critical_point_found"] is False
    assert result["stop_reason"] == "initial_power_flow_failure"


def test_failed_continuation_step_marks_stress_boundary_not_operating_point_failure(monkeypatch):
    network = pp.create_empty_network()
    bus = pp.create_bus(network, vn_kv=110)
    pp.create_ext_grid(network, bus)
    pp.create_load(network, bus, p_mw=10, q_mvar=1)
    runpp = pp.runpp

    def fail_only_under_stress(net, **kwargs):
        if float(net.load.p_mw.sum()) > 10.5:
            raise RuntimeError("synthetic stress limit")
        return runpp(net, **kwargs)

    monkeypatch.setattr(pp, "runpp", fail_only_under_stress)
    result = run_continuation_power_flow(network, step=0.05, max_steps=3)

    assert result["converged"] is True
    assert result["critical_point_found"] is True
    assert result["stop_reason"] == "power_flow_failure"
    assert result["failure_lambda"] == pytest.approx(1.1)
    assert result["voltage_margin_pct"] == pytest.approx(5)
