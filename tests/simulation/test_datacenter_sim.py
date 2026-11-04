import simpy
import pytest

from src.domain.datacenter import DataCenter
from src.domain.device import DeviceSpec
from src.domain.enums import TaskStatus
from src.domain.task import Task
from src.simulation.datacenter_sim import DataCenterSim


class _Adapter:
    def __init__(self):
        self.power_flow_runs = 0
    def update_compute_load(self, *args):
        pass
    def run_power_flow(self):
        self.power_flow_runs += 1
    def get_bus_carbon_intensity(self, bus):
        return 0.5


class _Bandwidth:
    def request_bandwidth(self, dc_id, task):
        yield self
    def release_bandwidth(self, *args):
        pass


def test_duration_hours_are_converted_to_simulation_seconds():
    env = simpy.Environment()
    sim = DataCenterSim(env, DataCenter(id="dc", name="dc", total_compute=10), _Adapter(), _Bandwidth())
    task = Task(user_id="u", task_type="general", required_compute=1, duration_hours=0.5)
    env.process(sim.run_task(task))
    env.run(until=1)
    assert task in sim.running_tasks
    env.run(until=1800)
    assert task in sim.running_tasks
    env.run(until=1800.1)
    assert task not in sim.running_tasks


def test_runtime_uses_same_task_power_model_as_optimizer_projection():
    env = simpy.Environment(initial_time=100)
    center = DataCenter(
        id="dc", name="dc", total_compute=10,
        device_pool=[DeviceSpec(
            model="compute", equipment_type="compute", quantity=1,
            compute_tflops=10, rated_power_kw=2,
            power_trace=[
                {"time_s": 0, "power_kw": 1.0},
                {"time_s": 1, "power_kw": 2.0},
                {"time_s": 2, "power_kw": 9.0},
            ],
        )],
    )
    sim = DataCenterSim(env, center, _Adapter(), _Bandwidth())
    task = Task(
        user_id="u", task_type="general", required_compute=1,
        duration_hours=0.5,
    )
    task.transition_to(TaskStatus.SCHEDULING)
    expected = center.power_for_task_mw(task, elapsed_seconds=100.0)

    env.process(sim.run_task(task))
    env.run(until=100.1)

    assert task.actual_power_mw == expected
    assert sim.current_load_mw == expected


def test_runtime_remaps_power_each_second_and_integrates_energy():
    env = simpy.Environment()
    adapter = _Adapter()
    center = DataCenter(
        id="dc", name="dc", total_compute=10, pue=1.0,
        device_pool=[DeviceSpec(
            model="compute", equipment_type="compute", quantity=1,
            compute_tflops=10, rated_power_kw=9,
            power_trace=[
                {"time_s": 0, "power_kw": 1.0},
                {"time_s": 1, "power_kw": 2.0},
                {"time_s": 2, "power_kw": 9.0},
            ],
        )],
    )
    sim = DataCenterSim(env, center, adapter, _Bandwidth())
    task = Task(
        user_id="u", task_type="general", required_compute=10,
        duration_hours=2 / 3600,
    )
    task.transition_to(TaskStatus.SCHEDULING)

    env.process(sim.run_task(task))
    env.run(until=0.1)
    assert task.actual_power_mw == pytest.approx(0.001)
    assert sim.current_load_mw == pytest.approx(0.001)

    env.run(until=1.1)
    assert task.actual_power_mw == pytest.approx(0.002)
    assert sim.current_load_mw == pytest.approx(0.002)

    env.run(until=2.1)
    assert task.status is TaskStatus.COMPLETED
    assert task.actual_power_mw == pytest.approx(0.0015)
    assert sim.total_energy_mwh == pytest.approx((0.001 + 0.002) / 3600)
    assert sim.current_load_mw == pytest.approx(0.0)
    # Runtime load changes are batched into the engine's periodic AC refresh.
    assert adapter.power_flow_runs == 0


def test_runtime_uses_datacenter_step_seconds_for_event_spacing():
    env = simpy.Environment()
    adapter = _Adapter()
    sim = DataCenterSim(env, DataCenter(id="dc", name="dc", total_compute=10), adapter, _Bandwidth())
    sim.step_seconds = 5
    task = Task(user_id="u", task_type="general", required_compute=1, duration_hours=10 / 3600)
    task.transition_to(TaskStatus.SCHEDULING)

    env.process(sim.run_task(task))
    env.run(until=1)
    assert task in sim.running_tasks
    env.run(until=4.9)
    assert task in sim.running_tasks
    env.run(until=5.1)
    assert task in sim.running_tasks
    env.run(until=10.1)
    assert task.status is TaskStatus.COMPLETED
