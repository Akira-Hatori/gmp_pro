from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _read_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class DaemonConfig:
    host: str
    port: int
    matlab_session_name: str
    model_registry_path: Path
    default_timeout_sec: float
    api_token: str


@lru_cache(maxsize=1)
def get_daemon_config() -> DaemonConfig:
    base_dir = Path(__file__).resolve().parent
    registry_path = Path(
        os.getenv("SIM_MODEL_REGISTRY_PATH", str(base_dir / "model_registry.json"))
    ).expanduser()

    return DaemonConfig(
        host=os.getenv("SIM_DAEMON_HOST", "0.0.0.0").strip(),
        port=_read_int("SIM_DAEMON_PORT", 8000),
        matlab_session_name=os.getenv("SIM_MATLAB_SESSION_NAME", "").strip(),
        model_registry_path=registry_path,
        default_timeout_sec=_read_float("SIM_DEFAULT_TIMEOUT_SEC", 600.0),
        api_token=os.getenv("SIM_DAEMON_API_TOKEN", "").strip(),
    )
