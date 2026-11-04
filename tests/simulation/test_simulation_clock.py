from datetime import datetime

from src.simulation.engine import SimulationEngine


def test_engine_exposes_real_datetime_for_simulation_second():
    engine = object.__new__(SimulationEngine)
    engine.simulation_start_time = datetime(2026, 9, 22, 15, 54, 49)
    engine.current_second = 11

    assert engine.current_datetime().strftime("%Y-%m-%d %H:%M:%S") == "2026-09-22 15:55:00"
