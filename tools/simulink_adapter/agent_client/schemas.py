from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

SimulationStatus = Literal["done", "failed", "unknown"]


class SimulationRequest(BaseModel):
    model_ref: str = Field(..., description="Logical model reference key registered on daemon side")
    params: Optional[Dict[str, Any]] = Field(default=None)
    result_vars: List[str] = Field(default_factory=list)
    request_id: Optional[str] = None


class SimulationDiagnostics(BaseModel):
    error_msg: Optional[str] = None
    execution_time_sec: float = 0.0
    resolved_model: Optional[str] = None
    model_sim_status: Optional[str] = None
    matlab_console: str = ""
    matlab_error_report: str = ""
    matlab_lastwarn_msg: str = ""
    matlab_lastwarn_id: str = ""
    kpi_error_msg: Optional[str] = None


class SimulationResponse(BaseModel):
    status: SimulationStatus = "unknown"
    kpi: Dict[str, Any] = Field(default_factory=dict)
    diagnostics: SimulationDiagnostics = Field(default_factory=SimulationDiagnostics)
    outputs: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
