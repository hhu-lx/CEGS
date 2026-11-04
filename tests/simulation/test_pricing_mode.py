from src.domain.datacenter import DataCenter
from src.simulation.engine import SimulationEngine


class _Grid:
    def get_bus_marginal_price(self, bus_id):
        return 9.0


def test_fixed_tou_mode_overrides_variable_node_price():
    engine = object.__new__(SimulationEngine)
    engine.simulation_start_time = __import__("datetime").datetime(2026, 1, 1)
    engine.current_second = 12 * 3600
    engine.fixed_pricing = __import__("src.strategies.electricity.fixed_tou", fromlist=["FixedTimeOfUsePricing"]).FixedTimeOfUsePricing([
        {"start_hour": 0, "end_hour": 24, "price": 0.5}
    ])
    engine.data_centers = [DataCenter(id="dc", name="dc", total_compute=10)]
    engine.pp_adapter = _Grid()
    engine._update_data_center_prices()

    assert engine.data_centers[0].current_price > 0
    assert engine.data_centers[0].current_price == 0.5 * 1000 * 0.5 * 1.3


def test_set_pricing_accepts_a_user_csv_file():
    engine = object.__new__(SimulationEngine)

    engine.set_pricing({
        "mode": "fixed_tou",
        "file": "tests/fixtures/time_of_use_pricing.csv",
    })

    assert engine.fixed_pricing.price_at_hour(18) == 1.10
