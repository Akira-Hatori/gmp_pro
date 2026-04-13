from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _normalize_api_path(path: str) -> str:
    path = path.strip() if path else ""
    if not path:
        return "/api/v1/simulations"
    if not path.startswith("/"):
        path = "/" + path
    return path


@dataclass(frozen=True)
class AgentClientConfig:
    daemon_base_url: str
    timeout_sec: float
    api_token: str
    simulations_path: str

    @property
    def endpoint(self) -> str:
        return self.daemon_base_url.rstrip("/") + self.simulations_path


@lru_cache(maxsize=1)
def get_client_config() -> AgentClientConfig:
    base_url = os.getenv("SIM_DAEMON_BASE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    return AgentClientConfig(
        daemon_base_url=base_url,
        timeout_sec=_read_float("SIM_DAEMON_TIMEOUT_SEC", 120.0),
        api_token=os.getenv("SIM_DAEMON_API_TOKEN", "").strip(),
        simulations_path=_normalize_api_path(os.getenv("SIM_DAEMON_SIMULATIONS_PATH", "/api/v1/simulations")),
    )
