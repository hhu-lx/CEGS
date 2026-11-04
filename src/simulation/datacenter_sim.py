# src/simulation/datacenter_sim.py
import simpy
from typing import Optional
from src.domain.task import Task
from src.domain.enums import TaskStatus
from src.domain.datacenter import DataCenter
from src.infrastructure.pandapower_adapter import PandapowerAdapter
from src.simulation.network_sim import BandwidthManager
from src.strategies.mapping.base import MappingStrategy
from src.strategies.mapping.linear import LinearMapping


class DataCenterSim:

    def __init__(
        self,
        env: simpy.Environment,
        datacenter: DataCenter,
        pp_adapter: PandapowerAdapter,
        bandwidth_manager: BandwidthManager,
        mapping_strategy: Optional[MappingStrategy] = None
    ):

        self.env = env
        self.dc = datacenter
        self.pp_adapter = pp_adapter
        self.bandwidth_manager = bandwidth_manager

        # 算力资源
        self.compute_resource = simpy.Resource(env, capacity=datacenter.total_compute)

        # 状态跟踪
        self.current_load_mw = 0.0          # 当前节点总负荷（MW）
        self.running_tasks = []             # 正在运行的任务列表（用于统计）
        self.grid_bus_id = datacenter.grid_bus_id

        # 映射策略
        if mapping_strategy is None:
            # 默认使用 LinearMapping，基准系数取自数据中心的 power_per_tflops
            self.mapping_strategy = LinearMapping(
                base_coefficient=datacenter.power_per_tflops
            )
        else:
            self.mapping_strategy = mapping_strategy
        self.total_energy_mwh = 0.0
        self.total_emission_kg = 0.0


    def run_task(self, task: Task):
        # A task may be encountered twice if a caller accidentally schedules
        # the same SimPy process more than once. Claim it before the first
        # yield so concurrent duplicate processes cannot reserve resources.
        if task._simulation_started:
            print(f"[跳过] 任务 {task.id} 已进入仿真，不重复启动")
            return
        task._simulation_started = True

        #  申请算力资源
        compute_request = self.compute_resource.request()
        yield compute_request

        #  申请带宽资源（由 BandwidthManager 管理）
        bandwidth_request = yield from self._request_bandwidth(task)

        #开始执行
        # The engine normally reserves resources during dispatch.  Direct
        # callers (and older integrations) still get a safe local allocation.
        if not getattr(task, "_resources_reserved", False):
            self.dc.allocate(task)
            task._resources_reserved = True

        # 计算任务功率（使用映射策略，根据任务类型、GPU等）
        # Prefer measured/representative equipment curves when configured;
        # retain the legacy mapping strategy for older centres without a
        # device inventory.
        # Runtime uses the current simulation position in the repeating
        # equipment traces. Optimizers use the same model with the trace mean.
        task_power_mw = self.dc.power_for_task_mw(
            task, elapsed_seconds=float(self.env.now)
        )
        task.actual_power_mw = task_power_mw

        #更新电网负荷并执行潮流计算
        self.current_load_mw += task_power_mw
        self.pp_adapter.update_compute_load(self.grid_bus_id, self.current_load_mw)

        # 记录运行中的任务
        task.transition_to(TaskStatus.RUNNING)
        task.actual_start_second = float(self.env.now)
        self.running_tasks.append(task)

        # 打印开始日志
        task_type = getattr(task, 'task_type', 'unknown')
        gpu_info = f", GPU: {getattr(task, 'plan_gpu', 0)}%" if getattr(task, 'plan_gpu', 0) else ""
        print(
            f"[开始] [{self.env.now:.2f}s] 任务 {task.id[:8]} | "
            f"类型: {task_type} | "
            f"算力: {task.required_compute:.1f} TFLOPS | "
            f"负荷: {task_power_mw:.2f} MW | "
            f"数据中心: {self.dc.name}"
        )

        # 6. 模拟任务运行。设备功率时序按全局仿真秒逐点读取；这里只
        # 更新负荷状态，避免为了功率采样而每秒重复执行交流潮流。
        remaining_seconds = task.duration_hours * 3600.0
        task_energy_mwh = 0.0
        while remaining_seconds > 1e-9:
            step_seconds = min(
                float(getattr(self, "step_seconds", 1.0)),
                remaining_seconds,
            )
            yield self.env.timeout(step_seconds)
            task_energy_mwh += task_power_mw * step_seconds / 3600.0
            remaining_seconds -= step_seconds
            if remaining_seconds <= 1e-9:
                break

            next_power_mw = self.dc.power_for_task_mw(
                task, elapsed_seconds=float(self.env.now)
            )
            self.current_load_mw += next_power_mw - task_power_mw
            task_power_mw = next_power_mw
            task.actual_power_mw = task_power_mw
            self.pp_adapter.update_compute_load(
                self.grid_bus_id, self.current_load_mw
            )

        task.actual_power_mw = task_energy_mwh / task.duration_hours
        carbon_intensity = self.pp_adapter.get_bus_carbon_intensity(self.grid_bus_id)
        task_emission_kg = carbon_intensity * task_energy_mwh * 1000

        self.total_energy_mwh += task_energy_mwh
        self.total_emission_kg += task_emission_kg
        task.actual_end_second = float(self.env.now)
        task.actual_execution_seconds = task.actual_end_second - (task.actual_start_second or task.actual_end_second)
        task.transition_to(TaskStatus.COMPLETED)
        # 任务结束
        # 从运行列表中移除
        self.running_tasks.remove(task)

        # Release the same compute/bandwidth/GPU reservation made at dispatch.
        self.dc.release(task)

        # 释放电网负荷
        self.current_load_mw -= task_power_mw
        self.pp_adapter.update_compute_load(self.grid_bus_id, self.current_load_mw)

        # 释放带宽资源
        self.bandwidth_manager.release_bandwidth(self.dc.id, task, bandwidth_request)

        # 释放算力资源
        self.compute_resource.release(compute_request)

        print(
            f"[结束] [{self.env.now:.2f}s] 任务 {task.id[:8]} | "
            f"释放功耗: {task_power_mw:.2f} MW | "
            f"当前总负荷: {self.current_load_mw:.2f} MW"
            f"排放: {task_emission_kg:.1f} kgCO₂ | "
            f"累计排放: {self.total_emission_kg:.1f} kgCO₂"
        )

    def _request_bandwidth(self, task: Task):
        """Await a SimPy bandwidth event while tolerating simple test adapters."""
        request_process = self.bandwidth_manager.request_bandwidth(self.dc.id, task)
        if hasattr(request_process, "callbacks"):
            yield request_process
            return request_process
        iterator = iter(request_process)
        try:
            yielded = next(iterator)
        except StopIteration as stop:
            return stop.value
        while True:
            value = yield yielded if hasattr(yielded, "callbacks") else self.env.timeout(0)
            try:
                yielded = iterator.send(value)
            except StopIteration as stop:
                return stop.value


    def get_running_tasks(self):
        #返回当前正在运行的任务列表
        return self.running_tasks

    def get_current_load(self) -> float:
        #返回当前节点总负荷
        return self.current_load_mw

    def get_available_compute(self) -> float:
        #返回当前剩余算力
        return self.dc.available_compute

    def get_available_bandwidth(self) -> float:
        #返回当前剩余带宽
        return self.bandwidth_manager.get_available_bandwidth(self.dc.id)
