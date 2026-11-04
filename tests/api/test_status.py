from fastapi.testclient import TestClient

from src.app import create_app


class FakeEngine:
    def __init__(self):
        self.submitted = []

    def submit_task(self, task):
        self.submitted.append(task)

    def get_latest_stats(self):
        return {"second": 3, "total_load": 42.0}

    def get_total_carbon_summary(self):
        return {"total_energy_mwh": 2.0, "total_emission_kg": 1.0}

    def get_storage_summary(self):
        return {"storage-1": {"soc_mwh": 4.0, "current_power_mw": -1.0}}

    def get_optimization_result(self):
        return {"status": "optimal", "objective_value": 1.2}


def test_submit_and_query_platform_status():
    client = TestClient(create_app(FakeEngine()))
    response = client.post("/tasks", json={"user_id": "u", "task_type": "general", "compute_amount_tflop_hours": 1, "duration_hours": 1})

    assert response.status_code == 202
    assert client.get("/grid/latest").json()["total_load"] == 42.0
    assert client.get("/carbon/summary").json()["total_emission_kg"] == 1.0
    assert client.get("/storage").json()["storage-1"]["soc_mwh"] == 4.0
    assert client.get("/optimization/latest").json()["status"] == "optimal"
