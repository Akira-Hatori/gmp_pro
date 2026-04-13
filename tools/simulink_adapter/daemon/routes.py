from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException

try:
    from .config import get_daemon_config
    from .schemas import SimulationRequest, SimulationResponse
    from .task_manager import SimulationTaskManager
except ImportError:
    from config import get_daemon_config
    from schemas import SimulationRequest, SimulationResponse
    from task_manager import SimulationTaskManager

router = APIRouter()


def _check_api_token(x_api_token: Optional[str]) -> None:
    config = get_daemon_config()
    if config.api_token and x_api_token != config.api_token:
        raise HTTPException(status_code=401, detail="Invalid API token")


@router.get("/health")
def health() -> dict:
    manager = SimulationTaskManager.get_instance()
    return manager.health()


@router.post("/api/v1/simulations", response_model=SimulationResponse)
def submit_simulation(
    request: SimulationRequest,
    x_api_token: Optional[str] = Header(default=None, alias="X-API-Token"),
) -> SimulationResponse:
    _check_api_token(x_api_token)
    manager = SimulationTaskManager.get_instance()
    return manager.run_simulation(request)
