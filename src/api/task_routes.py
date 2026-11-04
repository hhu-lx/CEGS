from fastapi import APIRouter, HTTPException, Request, status

from src.data.synthetic_tasks import SyntheticTaskDataFactory
from src.domain.task import Task

router = APIRouter()


def _engine(request: Request):
    engine = getattr(request.app.state, "engine", None)
    if engine is None:
        raise HTTPException(status_code=503, detail="simulation engine is not configured")
    return engine


@router.post("/tasks", status_code=status.HTTP_202_ACCEPTED)
def submit_task(task: Task, request: Request):
    completed = SyntheticTaskDataFactory(seed=getattr(request.app.state, "synthetic_seed", 42)).complete(task)
    _engine(request).submit_task(completed)
    return {"status": "accepted", "task": completed.model_dump(mode="json")}


@router.get("/grid/latest")
def get_grid_status(request: Request):
    return _engine(request).get_latest_stats()


@router.get("/carbon/summary")
def get_carbon_summary(request: Request):
    return _engine(request).get_total_carbon_summary()


@router.get("/storage")
def get_storage_summary(request: Request):
    return _engine(request).get_storage_summary()


@router.get("/optimization/latest")
def get_optimization_result(request: Request):
    return _engine(request).get_optimization_result()


@router.get("/pricing")
def get_pricing(request: Request):
    """Return the active marginal or fixed time-of-use tariff."""
    return _engine(request).get_pricing()


@router.put("/pricing")
def set_pricing(payload: dict, request: Request):
    """Replace the user-editable electricity pricing configuration."""
    try:
        return _engine(request).set_pricing(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
