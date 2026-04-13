from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Optional

try:
    from .config import DaemonConfig, get_daemon_config
    from .schemas import SimulationDiagnostics, SimulationRequest, SimulationResponse
except ImportError:
    from config import DaemonConfig, get_daemon_config
    from schemas import SimulationDiagnostics, SimulationRequest, SimulationResponse

if TYPE_CHECKING:
    try:
        from .matlab_worker import SimulinkWorker
    except ImportError:
        from matlab_worker import SimulinkWorker


class SimulationTaskManager:
    _instance: Optional["SimulationTaskManager"] = None
    _instance_lock = threading.Lock()

    def __init__(self, config: DaemonConfig):
        self._config = config
        self._worker: Optional["SimulinkWorker"] = None
        self._worker_lock = threading.Lock()
        self._sim_lock = threading.Lock()
        self._registry_error = ""
        self._model_registry = self._load_model_registry(config.model_registry_path)

    @classmethod
    def get_instance(cls, config: Optional[DaemonConfig] = None) -> "SimulationTaskManager":
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls(config or get_daemon_config())
            return cls._instance

    def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "registry_size": len(self._model_registry),
            "registry_error": self._registry_error,
            "worker_initialized": self._worker is not None,
        }

    def run_simulation(self, request: SimulationRequest) -> SimulationResponse:
        wall_start = time.perf_counter()

        try:
            model_path = self._resolve_model_path(request.model_ref)
            model_name = Path(model_path).stem

            with self._sim_lock:
                worker = self._get_worker()
                worker_result = worker.run_simulation(
                    model_name=model_name,
                    params=dict(request.params or {}),
                    model_path=model_path,
                    result_vars=list(request.result_vars),
                )

            return self._normalize_worker_result(
                request_id=request.request_id,
                worker_result=worker_result,
                fallback_elapsed=time.perf_counter() - wall_start,
            )

        except Exception as exc:
            diagnostics = SimulationDiagnostics(
                error_msg=str(exc),
                execution_time_sec=round(time.perf_counter() - wall_start, 3),
            )
            return SimulationResponse(
                status="failed",
                kpi={},
                diagnostics=diagnostics,
                outputs={},
                request_id=request.request_id,
            )

    def _get_worker(self) -> "SimulinkWorker":
        with self._worker_lock:
            if self._worker is None:
                try:
                    from .matlab_worker import SimulinkWorker as WorkerType
                except ImportError:
                    from matlab_worker import SimulinkWorker as WorkerType

                self._worker = WorkerType()
            return self._worker

    def _resolve_model_path(self, model_ref: str) -> str:
        if not self._model_registry:
            if self._registry_error:
                raise RuntimeError(f"Model registry unavailable: {self._registry_error}")
            raise KeyError("Model registry is empty")

        model_path = self._model_registry.get(model_ref)
        if not model_path:
            raise KeyError(f"Unknown model_ref: {model_ref}")

        path_obj = Path(model_path).expanduser()
        if not path_obj.is_absolute():
            path_obj = (Path(__file__).resolve().parent / path_obj).resolve()

        if path_obj.suffix.lower() != ".slx":
            raise ValueError(f"Mapped model is not a .slx file: {path_obj}")
        if not path_obj.exists():
            raise FileNotFoundError(f"Mapped model file not found: {path_obj}")

        return str(path_obj)

    def _load_model_registry(self, registry_path: Path) -> Dict[str, str]:
        try:
            path_obj = registry_path.expanduser()
            if not path_obj.is_absolute():
                path_obj = (Path(__file__).resolve().parent / path_obj).resolve()

            if not path_obj.exists():
                self._registry_error = f"registry file not found: {path_obj}"
                return {}

            with path_obj.open("r", encoding="utf-8") as fh:
                raw = json.load(fh)

            if isinstance(raw, dict) and isinstance(raw.get("models"), dict):
                raw = raw["models"]

            if not isinstance(raw, dict):
                self._registry_error = "registry JSON must be an object"
                return {}

            normalized: Dict[str, str] = {}
            for key, value in raw.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    continue
                normalized[key] = value

            self._registry_error = ""
            return normalized

        except Exception as exc:
            self._registry_error = str(exc)
            return {}

    def _normalize_worker_result(
        self,
        request_id: Optional[str],
        worker_result: Dict[str, Any],
        fallback_elapsed: float,
    ) -> SimulationResponse:
        raw_diagnostics = worker_result.get("diagnostics")
        if not isinstance(raw_diagnostics, dict):
            raw_diagnostics = {}

        diagnostics = SimulationDiagnostics(
            error_msg=raw_diagnostics.get("error_msg"),
            execution_time_sec=float(
                raw_diagnostics.get("execution_time_sec")
                if raw_diagnostics.get("execution_time_sec") is not None
                else round(fallback_elapsed, 3)
            ),
            resolved_model=raw_diagnostics.get("resolved_model"),
            model_sim_status=raw_diagnostics.get("model_sim_status"),
            matlab_console=str(raw_diagnostics.get("matlab_console") or ""),
            matlab_error_report=str(raw_diagnostics.get("matlab_error_report") or ""),
            matlab_lastwarn_msg=str(raw_diagnostics.get("matlab_lastwarn_msg") or ""),
            matlab_lastwarn_id=str(raw_diagnostics.get("matlab_lastwarn_id") or ""),
            kpi_error_msg=raw_diagnostics.get("kpi_error_msg"),
        )

        kpi = worker_result.get("kpi")
        if not isinstance(kpi, dict):
            kpi = {}

        outputs = worker_result.get("outputs")
        if not isinstance(outputs, dict):
            outputs = {}

        status = str(worker_result.get("status", "failed"))
        if status not in {"done", "failed", "unknown"}:
            status = "failed"

        return SimulationResponse(
            status=status,
            kpi=kpi,
            diagnostics=diagnostics,
            outputs=outputs,
            request_id=request_id,
        )
