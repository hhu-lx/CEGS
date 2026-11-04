from src.domain.storage import EnergyStorage
from src.optimization.copt_optimizer import CoptOptimizer


def test_copt_storage_dispatch_respects_soc_and_never_charges_and_discharges_together():
    storage = EnergyStorage(id="s", bus_id=3, capacity_mwh=10, max_power_mw=4, initial_soc_mwh=2, min_soc_mwh=1)

    result = CoptOptimizer().optimize_storage(storage, prices=[0.1, 1.0], step_hours=1)

    assert result.status == "optimal"
    assert result.charge_mw[0] > 0
    assert result.discharge_mw[0] == 0
    assert result.charge_mw[1] == 0
    assert result.discharge_mw[1] > 0
    assert all(charge == 0 or discharge == 0 for charge, discharge in zip(result.charge_mw, result.discharge_mw))
    assert all(storage.min_soc_mwh <= soc <= storage.max_soc_mwh for soc in result.soc_mwh)
