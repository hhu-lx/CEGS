from src.domain.datacenter import DataCenter
from src.domain.task import Task
from src.strategies.allocation.carbon_aware import CarbonAwareStrategy
from src.strategies.allocation.lowest_price import LowestPriceStrategy
from src.simulation.scheduler import Scheduler
import pytest


def test_carbon_aware_strategy_selects_eligible_lowest_carbon_center():
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    high_carbon = DataCenter(id="high", name="high", total_compute=10, grid_bus_id=3)
    low_carbon = DataCenter(id="low", name="low", total_compute=10, grid_bus_id=4)
    snapshot = {"carbon_intensity": {high_carbon.grid_bus_id: 0.8, low_carbon.grid_bus_id: 0.1}}

    choice = CarbonAwareStrategy().allocate(task, [high_carbon, low_carbon], snapshot)

    assert choice.id == "low"


def test_lowest_price_error_reports_resource_snapshot():
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=12, duration_hours=1)
    center = DataCenter(id="dc", name="dc", total_compute=10)
    with pytest.raises(Exception, match=r"required_compute=12.*dc: compute=10/10"):
        LowestPriceStrategy().allocate(task, [center])


def test_scheduler_forwards_runtime_snapshot_to_configured_strategy():
    task = Task(user_id="u", task_type="general", compute_amount_tflop_hours=1, duration_hours=1)
    high_carbon = DataCenter(id="high", name="high", total_compute=10, grid_bus_id=3)
    low_carbon = DataCenter(id="low", name="low", total_compute=10, grid_bus_id=4)
    scheduler = Scheduler(CarbonAwareStrategy())

    choice = scheduler.select_data_center(
        task,
        [high_carbon, low_carbon],
        {"carbon_intensity": {3: 0.8, 4: 0.1}},
    )

    assert choice.id == "low"
