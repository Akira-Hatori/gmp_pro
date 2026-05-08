from __future__ import annotations

import json
import os
import re
import tempfile
import time
from typing import Any, Dict, List, Optional, Tuple

import matlab.engine

_MATLAB_VAR_RE = re.compile(r"^[A-Za-z]\w*$")


class LocalSimulinkRunner:
    """Run a local Simulink model and collect diagnostics plus scope signals."""

    def __init__(self, matlab_session_name: Optional[str] = None):
        sessions = matlab.engine.find_matlab()
        if not sessions:
            raise RuntimeError(
                "No shared MATLAB session found. In MATLAB run: matlab.engine.shareEngine"
            )

        if matlab_session_name:
            if matlab_session_name not in sessions:
                raise RuntimeError(
                    f"Requested MATLAB session '{matlab_session_name}' not found. Available: {sessions}"
                )
            target_session = matlab_session_name
        else:
            target_session = sessions[0]

        self.session_name = target_session
        self.eng = matlab.engine.connect_matlab(target_session)

    def run_model(
        self,
        model_path: str,
        scope_channel_map: Dict[str, List[str]],
        scope_vars: Optional[List[str]] = None,
        open_model_ui: bool = True,
    ) -> Dict[str, Any]:
        resolved_model = self._prepare_model(model_path=model_path, open_model_ui=open_model_ui)

        diagnostics: Dict[str, Any] = {
            "error_msg": None,
            "execution_time_sec": 0.0,
            "resolved_model": resolved_model,
            "matlab_console": "",
            "matlab_error_report": "",
            "matlab_lastwarn_msg": "",
            "matlab_lastwarn_id": "",
            "model_sim_status": "unknown",
            "matlab_session": self.session_name,
        }

        start = time.time()
        sim_capture = self._run_with_console_capture(resolved_model)
        diagnostics["execution_time_sec"] = round(time.time() - start, 3)
        diagnostics["matlab_console"] = sim_capture["console"]
        diagnostics["matlab_error_report"] = sim_capture["error_report"]
        diagnostics["matlab_lastwarn_msg"] = sim_capture["lastwarn_msg"]
        diagnostics["matlab_lastwarn_id"] = sim_capture["lastwarn_id"]
        diagnostics["model_sim_status"] = sim_capture["model_sim_status"]

        status = "done" if sim_capture["sim_status"] == "done" else "failed"
        if status == "failed":
            diagnostics["error_msg"] = sim_capture["error_report"] or "MATLAB simulation failed"

        actual_scope_vars = list(scope_vars or scope_channel_map.keys())
        raw_scopes: Dict[str, Any] = {}
        for scope_var in actual_scope_vars:
            raw_scopes[scope_var] = self._read_workspace_var_as_json(scope_var)

        merged_signals, mapping_errors = self._merge_scope_signals(raw_scopes, scope_channel_map)

        return {
            "status": status,
            "diagnostics": diagnostics,
            "signals": merged_signals,
            "raw_scopes": raw_scopes,
            "scope_mapping_errors": mapping_errors,
        }

    def _prepare_model(self, model_path: str, open_model_ui: bool) -> str:
        normalized = os.path.abspath(os.path.normpath(model_path))
        if not os.path.exists(normalized):
            raise FileNotFoundError(f"Model file not found: {normalized}")

        model_dir, model_file = os.path.split(normalized)
        model_name, ext = os.path.splitext(model_file)
        if ext.lower() != ".slx":
            raise ValueError(f"Only .slx model is supported, got: {model_file}")

        matlab_model_dir = model_dir.replace("\\", "/")
        self.eng.cd(matlab_model_dir, nargout=0)
        self.eng.addpath(matlab_model_dir, nargout=0)
        self.eng.load_system(model_name, nargout=0)

        if open_model_ui:
            try:
                self.eng.open_system(model_name, nargout=0)
            except Exception:
                pass

        return model_name

    def _run_with_console_capture(self, model_name: str) -> Dict[str, str]:
        self.eng.lastwarn("", nargout=0)

        with tempfile.NamedTemporaryFile(prefix="gmp_local_sil_", suffix=".log", delete=False) as fh:
            diary_file = fh.name

        diary_file_matlab = diary_file.replace("\\", "/")

        try:
            self.eng.diary(diary_file_matlab, nargout=0)
            self.eng.diary("on", nargout=0)
        except Exception:
            diary_file = ""

        sim_status = "done"
        sim_error = ""
        sim_console = ""

        try:
            self.eng.eval(f"out = sim('{model_name}'); assignin('base', 'out', out);", nargout=0)
        except matlab.engine.MatlabExecutionError as exc:
            sim_status = "failed"
            sim_error = str(exc)
        finally:
            try:
                self.eng.diary("off", nargout=0)
            except Exception:
                pass

        if diary_file and os.path.exists(diary_file):
            try:
                with open(diary_file, "r", encoding="utf-8", errors="ignore") as fh:
                    sim_console = fh.read()
            finally:
                try:
                    os.remove(diary_file)
                except Exception:
                    pass

        lastwarn_msg = ""
        lastwarn_id = ""
        try:
            lastwarn_msg, lastwarn_id = self.eng.lastwarn(nargout=2)
        except Exception:
            pass

        model_sim_status = "unknown"
        try:
            model_sim_status = self.eng.get_param(model_name, "SimulationStatus", nargout=1)
        except Exception:
            pass

        return {
            "sim_status": sim_status,
            "console": self._trim_text(sim_console),
            "error_report": self._trim_text(sim_error),
            "lastwarn_msg": self._trim_text(lastwarn_msg, max_len=2000),
            "lastwarn_id": self._trim_text(lastwarn_id, max_len=500),
            "model_sim_status": str(model_sim_status),
        }

    def _read_workspace_var_as_json(self, var_name: str) -> Any:
        if not _MATLAB_VAR_RE.match(var_name):
            return {"_error": f"Invalid MATLAB variable name: {var_name}"}

        self.eng.workspace["gmp_scope_var_name"] = var_name
        self.eng.eval(
            """
gmp_scope_json = "";
try
    gmp_scope_name = gmp_scope_var_name;
    gmp_v = [];
    gmp_found = false;

    try
        gmp_v = evalin("base", gmp_scope_name);
        gmp_found = true;
    catch
    end

    if ~gmp_found
        try
            gmp_out = evalin("base", "out");

            if isa(gmp_out, "Simulink.SimulationOutput")
                try
                    gmp_v = gmp_out.get(gmp_scope_name);
                    gmp_found = true;
                catch
                end
            elseif isstruct(gmp_out) && isfield(gmp_out, gmp_scope_name)
                gmp_v = gmp_out.(gmp_scope_name);
                gmp_found = true;
            end

            if ~gmp_found
                gmp_available = {};
                if isa(gmp_out, "Simulink.SimulationOutput")
                    try
                        gmp_available = who(gmp_out);
                    catch
                    end
                elseif isstruct(gmp_out)
                    gmp_available = fieldnames(gmp_out);
                end

                if isempty(gmp_available)
                    error("GMP:ScopeVarNotFound", "Scope variable '%s' not found in base workspace or out.", gmp_scope_name);
                else
                    error("GMP:ScopeVarNotFound", "Scope variable '%s' not found. Available in out: %s", gmp_scope_name, strjoin(cellstr(gmp_available), ", "));
                end
            end
        catch gmp_outer_me
            error(gmp_outer_me.identifier, gmp_outer_me.message);
        end
    end

    if isa(gmp_v, "timeseries")
        gmp_out = struct("time", gmp_v.Time, "signals", struct("label", "CH1", "values", gmp_v.Data));

    elseif isa(gmp_v, "Simulink.SimulationData.Dataset")
        gmp_n = numElements(gmp_v);
        gmp_sig = struct("label", {}, "values", {});
        gmp_time = [];
        for gmp_i = 1:gmp_n
            gmp_e = get(gmp_v, gmp_i);
            gmp_val = gmp_e.Values;
            gmp_label = char(gmp_e.Name);
            if isempty(gmp_label)
                gmp_label = sprintf("CH%d", gmp_i);
            end

            if isa(gmp_val, "timeseries")
                if isempty(gmp_time)
                    gmp_time = gmp_val.Time;
                end
                gmp_sig(gmp_i).label = gmp_label;
                gmp_sig(gmp_i).values = gmp_val.Data;
            else
                gmp_sig(gmp_i).label = gmp_label;
                gmp_sig(gmp_i).values = gmp_val;
            end
        end
        gmp_out = struct("time", gmp_time, "signals", gmp_sig);

    elseif isstruct(gmp_v)
        gmp_out = gmp_v;

    else
        gmp_out = struct("value", gmp_v);
    end

    gmp_scope_json = jsonencode(gmp_out);
catch gmp_me
    gmp_scope_json = jsonencode(struct("error", gmp_me.message));
end
""",
            nargout=0,
        )

        try:
            json_text = str(self.eng.workspace["gmp_scope_json"])
            payload = json.loads(json_text)
            if isinstance(payload, dict) and "error" in payload and "_error" not in payload:
                payload["_error"] = str(payload.get("error", ""))
            return payload
        except Exception as exc:
            return {"_error": f"JSON decode failed for {var_name}: {exc}"}
        finally:
            self.eng.eval(
                "clear gmp_scope_var_name gmp_scope_json gmp_scope_name gmp_v gmp_found gmp_out gmp_available gmp_n gmp_sig gmp_time gmp_i gmp_e gmp_val gmp_label gmp_me gmp_outer_me",
                nargout=0,
            )

    def _merge_scope_signals(
        self,
        raw_scopes: Dict[str, Any],
        scope_channel_map: Dict[str, List[str]],
    ) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
        merged: Dict[str, Dict[str, Any]] = {}
        errors: List[str] = []

        for scope_name, scope_obj in raw_scopes.items():
            if isinstance(scope_obj, dict) and scope_obj.get("_error"):
                errors.append(f"{scope_name}: {scope_obj['_error']}")
                continue

            channels = self._extract_channels(scope_obj)
            if not channels:
                errors.append(f"{scope_name}: no channel data found")
                continue

            semantic_names = scope_channel_map.get(scope_name, [])
            for idx, channel in enumerate(channels):
                if idx < len(semantic_names) and semantic_names[idx]:
                    signal_name = semantic_names[idx]
                else:
                    signal_name = f"{scope_name}.ch{idx + 1}"

                signal_name = self._dedupe_key(merged, signal_name)
                merged[signal_name] = {
                    "time": channel["time"],
                    "values": channel["values"],
                    "source_scope": scope_name,
                    "source_channel": channel["label"],
                }

        return merged, errors

    def _extract_channels(self, scope_obj: Any) -> List[Dict[str, Any]]:
        if not isinstance(scope_obj, dict):
            return []

        time_axis = self._to_1d(scope_obj.get("time", []))
        signals = scope_obj.get("signals")

        if signals is None:
            value_matrix = self._to_2d(scope_obj.get("value", []))
            return self._columns_to_channels(value_matrix, time_axis, "CH")

        if isinstance(signals, dict):
            signals = [signals]
        if not isinstance(signals, list):
            return []

        channels: List[Dict[str, Any]] = []
        for item in signals:
            if not isinstance(item, dict):
                continue

            label = str(item.get("label") or item.get("blockName") or "CH")
            value_matrix = self._to_2d(item.get("values", []))
            if not value_matrix:
                continue

            # Common Scope shape: one signal entry with Nx2 values.
            if len(signals) == 1 and len(value_matrix[0]) > 1:
                channels.extend(self._columns_to_channels(value_matrix, time_axis, label))
            elif len(value_matrix[0]) > 1:
                channels.extend(self._columns_to_channels(value_matrix, time_axis, label))
            else:
                values = [row[0] for row in value_matrix]
                channels.append({"label": label, "time": time_axis, "values": values})

        return channels

    @staticmethod
    def _columns_to_channels(
        matrix: List[List[float]], time_axis: List[float], label_prefix: str
    ) -> List[Dict[str, Any]]:
        if not matrix:
            return []

        cols = len(matrix[0])
        channels: List[Dict[str, Any]] = []
        for c in range(cols):
            values = [row[c] for row in matrix]
            channels.append(
                {
                    "label": f"{label_prefix}{c + 1}",
                    "time": time_axis,
                    "values": values,
                }
            )
        return channels

    @staticmethod
    def _to_1d(data: Any) -> List[float]:
        if data is None:
            return []
        if isinstance(data, list):
            if data and isinstance(data[0], list):
                return [LocalSimulinkRunner._to_float(row[0]) for row in data if row]
            return [LocalSimulinkRunner._to_float(v) for v in data]
        return [LocalSimulinkRunner._to_float(data)]

    @staticmethod
    def _to_2d(data: Any) -> List[List[float]]:
        if data is None:
            return []
        if isinstance(data, list):
            if not data:
                return []
            if isinstance(data[0], list):
                return [[LocalSimulinkRunner._to_float(v) for v in row] for row in data]
            return [[LocalSimulinkRunner._to_float(v)] for v in data]
        return [[LocalSimulinkRunner._to_float(data)]]

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            return float(value)
        except Exception:
            return 0.0

    @staticmethod
    def _dedupe_key(container: Dict[str, Any], base: str) -> str:
        if base not in container:
            return base
        idx = 2
        while f"{base}_{idx}" in container:
            idx += 1
        return f"{base}_{idx}"

    @staticmethod
    def _trim_text(text: Any, max_len: int = 20000) -> str:
        if text is None:
            return ""
        text = str(text)
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n...<truncated>..."
