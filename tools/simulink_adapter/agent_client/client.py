from __future__ import annotations

from typing import Any, Dict, Optional

import requests

try:
    from .config import AgentClientConfig, get_client_config
    from .schemas import SimulationRequest, SimulationResponse
except ImportError:
    from config import AgentClientConfig, get_client_config
    from schemas import SimulationRequest, SimulationResponse


class SimulationClientError(RuntimeError):
    pass


def _model_dump(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_validate(model_type: Any, data: Dict[str, Any]) -> Any:
    if hasattr(model_type, "model_validate"):
        return model_type.model_validate(data)
    return model_type.parse_obj(data)


class SimulationClient:
    def __init__(self, config: Optional[AgentClientConfig] = None):
        self._config = config or get_client_config()

    def submit(self, request: SimulationRequest) -> SimulationResponse:
        headers = {"Content-Type": "application/json"}
        if self._config.api_token:
            headers["X-API-Token"] = self._config.api_token

        try:
            response = requests.post(
                self._config.endpoint,
                json=_model_dump(request),
                headers=headers,
                timeout=self._config.timeout_sec,
            )
        except requests.Timeout as exc:
            raise SimulationClientError(
                f"Request timed out after {self._config.timeout_sec} seconds"
            ) from exc
        except requests.RequestException as exc:
            raise SimulationClientError(f"Network error while calling daemon: {exc}") from exc

        data = self._parse_json(response)
        if response.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else str(data)
            raise SimulationClientError(f"Daemon HTTP {response.status_code}: {detail}")

        try:
            return _model_validate(SimulationResponse, data)
        except Exception as exc:
            raise SimulationClientError(f"Invalid daemon response schema: {exc}") from exc

    @staticmethod
    def _parse_json(response: requests.Response) -> Dict[str, Any]:
        try:
            payload = response.json()
        except ValueError as exc:
            raise SimulationClientError("Daemon response is not valid JSON") from exc

        if not isinstance(payload, dict):
            raise SimulationClientError("Daemon response must be a JSON object")
        return payload


def submit_simulation(
    model_ref: str,
    params: Optional[Dict[str, Any]] = None,
    result_vars: Optional[list[str]] = None,
    request_id: Optional[str] = None,
    config: Optional[AgentClientConfig] = None,
) -> SimulationResponse:
    request = SimulationRequest(
        model_ref=model_ref,
        params=params,
        result_vars=result_vars or [],
        request_id=request_id,
    )
    client = SimulationClient(config=config)
    return client.submit(request)
