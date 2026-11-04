"""The shipped grid case should have a valid operating point for normal data."""

from src.infrastructure.pandapower_adapter import PandapowerAdapter


class ConstantLoader:
    def __init__(self, value: float):
        self.value = value

    def get_value_at_second(self, second: int) -> float:
        return self.value


def test_default_grid_has_feasible_ac_point_with_typical_time_series():
    # Values taken from the project's second 107 input records.
    adapter = PandapowerAdapter(
        load_loader=ConstantLoader(0.475127),
        pv_loader=ConstantLoader(0.0),
        wind_loader=ConstantLoader(0.399189),
        base_generation_loader=ConstantLoader(0.90109354),
    )
    adapter.update_time_series(107)
    adapter.run_power_flow()

    assert adapter.get_operating_constraint_snapshot()["feasible"] is True
    for index, generator in adapter.network.gen.iterrows():
        reactive_mvar = adapter.network.res_gen.at[index, "q_mvar"]
        assert generator.min_q_mvar - 1e-3 <= reactive_mvar <= generator.max_q_mvar + 1e-3
