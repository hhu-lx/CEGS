from src.domain.storage import EnergyStorage


def test_storage_caps_discharge_at_available_energy():
    storage = EnergyStorage(
        id="s1", bus_id=3, capacity_mwh=10, max_power_mw=8,
        initial_soc_mwh=2, min_soc_mwh=1, charge_efficiency=0.9,
        discharge_efficiency=0.9,
    )

    actual = storage.apply_power(requested_mw=8, step_hours=1)

    assert actual == 0.9
    assert storage.soc_mwh == 1


def test_storage_caps_charge_at_remaining_capacity():
    storage = EnergyStorage(id="s1", bus_id=3, capacity_mwh=10, max_power_mw=8, initial_soc_mwh=9)

    actual = storage.apply_power(requested_mw=-8, step_hours=1)

    assert actual == -1 / storage.charge_efficiency
    assert storage.soc_mwh == 10
