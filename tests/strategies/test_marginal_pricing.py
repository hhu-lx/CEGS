import pytest

from src.infrastructure.pandapower_adapter import PandapowerAdapter
from src.strategies.electricity.custom_parameterized import GridResponsivePricing
from src.strategies.electricity.fixed_tou import FixedTimeOfUsePricing
from src.strategies.electricity.marginal import MarginalElectricityPricing
from src.strategies.electricity.opf import OPFElectricityPricing


def _pricing() -> MarginalElectricityPricing:
    return MarginalElectricityPricing(
        sensitivity=0.10,
        scale=1000.0,
        base_pricing=FixedTimeOfUsePricing([
            {"start_hour": 0, "end_hour": 24, "price": 1.00},
        ]),
    )


def test_marginal_price_equals_tou_base_without_compute_load():
    """Catches a missing zero-load path that inflates the shared TOU baseline."""
    assert _pricing().get_node_price(None, 3, 0.0, 0.0) == 1.00


def test_marginal_price_combines_system_and_node_load_feedback():
    """Catches a price that omits either the shared-system or local-node term."""
    assert _pricing().get_node_price(None, 3, 100.0, 300.0) == pytest.approx(1.02)


def test_marginal_price_ignores_negative_load_feedback():
    """Catches negative injections incorrectly discounting the TOU electricity price."""
    assert _pricing().get_node_price(None, 3, -100.0, -300.0) == 1.00


def test_marginal_price_forecast_uses_tou_base_and_system_feedback():
    """Catches rolling dispatch forecasts retaining the superseded additive rule."""
    assert _pricing().forecast_prices([300.0]) == pytest.approx([1.015])


def test_adapter_passes_total_positive_compute_load_to_marginal_strategy():
    """Catches the adapter passing only local load and losing the system feedback term."""
    adapter = object.__new__(PandapowerAdapter)
    adapter.extra_loads = {3: 100.0, 16: 200.0, 21: -50.0}
    adapter.network = None
    adapter.electricity_strategy = _pricing()

    assert adapter.get_bus_marginal_price(3) == pytest.approx(1.02)


@pytest.mark.parametrize(
    "pricing",
    [GridResponsivePricing(), OPFElectricityPricing()],
)
def test_non_marginal_pricing_strategies_accept_adapter_system_load_argument(pricing):
    """Catches adapter aggregation breaking pre-existing pricing strategies."""
    assert pricing.get_node_price(None, 3, 10.0, 100.0) >= 0.0
