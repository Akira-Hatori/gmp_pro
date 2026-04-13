# matlab_worker.py
import os
import tempfile
import time
from typing import Any

import matlab.engine


class SimulinkWorker:
    def __init__(self):
        print("[Worker] 正在连接本地已共享的 MATLAB 会话...")
        try:
            sessions = matlab.engine.find_matlab()
            if not sessions:
                raise Exception("未找到共享的 MATLAB 会话！请在 MATLAB 中执行 matlab.engine.shareEngine")
            self.eng = matlab.engine.connect_matlab(sessions[0])
            print(f"[Worker] 成功连接到 MATLAB 会话: {sessions[0]}")
        except Exception as e:
            print(f"[Worker] 连接 MATLAB 失败: {e}")
            raise

    def _prepare_model(self, model_name: str, model_path: str | None = None) -> str:
        """
        准备 Simulink 模型并返回可用于 sim() 的模型名。
        支持两种调用：
        1) 仅传 model_name（要求 MATLAB path 可解析）
        2) 传 model_path（推荐，按绝对路径加载）
        """
        if model_path:
            normalized_path = os.path.normpath(model_path)
            if not os.path.isabs(normalized_path):
                normalized_path = os.path.abspath(normalized_path)
            if not os.path.exists(normalized_path):
                raise FileNotFoundError(f"模型文件不存在: {normalized_path}")

            model_dir, model_file = os.path.split(normalized_path)
            file_stem, ext = os.path.splitext(model_file)
            if ext.lower() != ".slx":
                raise ValueError(f"仅支持 .slx 模型文件，当前为: {model_file}")

            matlab_model_dir = model_dir.replace("\\", "/")
            self.eng.cd(matlab_model_dir, nargout=0)
            self.eng.addpath(matlab_model_dir, nargout=0)
            self.eng.load_system(file_stem, nargout=0)
            try:
                self.eng.open_system(file_stem, nargout=0)
            except Exception:
                pass
            return file_stem

        self.eng.load_system(model_name, nargout=0)
        try:
            self.eng.open_system(model_name, nargout=0)
        except Exception:
            pass
        return model_name

    def _trim_text(self, text: Any, max_len: int = 12000) -> str:
        if text is None:
            return ""
        text = str(text)
        if len(text) <= max_len:
            return text
        return text[:max_len] + "\n...<truncated>..."

    def _workspace_get(self, name: str, default: Any = None) -> Any:
        try:
            return self.eng.workspace[name]
        except Exception:
            return default

    def _matlab_run_with_capture(self, resolved_model: str) -> dict:
        self.eng.lastwarn("", nargout=0)

        with tempfile.NamedTemporaryFile(prefix="gmp_simulink_", suffix=".log", delete=False) as f:
            diary_file = f.name

        diary_file_matlab = diary_file.replace("\\", "/")

        try:
            self.eng.diary(diary_file_matlab, nargout=0)
            self.eng.diary("on", nargout=0)
        except Exception:
            diary_file = ""

        sim_status = "done"
        sim_console = ""
        sim_error = ""
        try:
            self.eng.sim(resolved_model, nargout=0)
        except matlab.engine.MatlabExecutionError as me:
            sim_status = "failed"
            sim_error = str(me)
        finally:
            try:
                self.eng.diary("off", nargout=0)
            except Exception:
                pass

        if diary_file and os.path.exists(diary_file):
            try:
                with open(diary_file, "r", encoding="utf-8", errors="ignore") as fh:
                    sim_console = fh.read()
            except Exception:
                sim_console = ""
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
            model_sim_status = self.eng.get_param(resolved_model, "SimulationStatus", nargout=1)
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

    def _collect_result_vars(self, result_vars: list[str] | None = None) -> dict:
        if not result_vars:
            return {}

        outputs: dict[str, Any] = {}
        for var_name in result_vars:
            value = self._workspace_get(var_name, default=None)
            if value is None:
                outputs[var_name] = None
                continue

            if isinstance(value, (int, float, str, bool)):
                outputs[var_name] = value
            else:
                outputs[var_name] = self._trim_text(repr(value), max_len=2000)

        return outputs

    def run_simulation(
        self,
        model_name: str,
        params: dict | None,
        model_path: str | None = None,
        result_vars: list[str] | None = None,
    ) -> dict:
        """
        执行一轮仿真，并采集 MATLAB/Simulink 诊断信息。
        """
        print(f"\n[Worker] 准备运行模型: {model_name}")
        if model_path:
            print(f"[Worker] 模型路径: {model_path}")

        result = {
            "status": "unknown",
            "kpi": {},
            "diagnostics": {
                "error_msg": None,
                "execution_time_sec": 0,
                "resolved_model": None,
                "model_sim_status": None,
                "matlab_console": "",
                "matlab_error_report": "",
                "matlab_lastwarn_msg": "",
                "matlab_lastwarn_id": "",
            },
            "outputs": {},
        }

        try:
            resolved_model = self._prepare_model(model_name=model_name, model_path=model_path)
            result["diagnostics"]["resolved_model"] = resolved_model

            if params:
                print("[Worker] 提示: 当前模式下 params 已忽略，控制量由外部内核提供")

            print("[Worker] 仿真运行中，请等待...")
            start_time = time.time()
            sim_capture = self._matlab_run_with_capture(resolved_model)

            run_time = round(time.time() - start_time, 2)
            result["diagnostics"]["execution_time_sec"] = run_time
            result["diagnostics"]["model_sim_status"] = sim_capture["model_sim_status"]
            result["diagnostics"]["matlab_console"] = sim_capture["console"]
            result["diagnostics"]["matlab_error_report"] = sim_capture["error_report"]
            result["diagnostics"]["matlab_lastwarn_msg"] = sim_capture["lastwarn_msg"]
            result["diagnostics"]["matlab_lastwarn_id"] = sim_capture["lastwarn_id"]
            print(f"[Worker] 仿真结束，耗时: {run_time} 秒")

            if sim_capture["sim_status"] != "done":
                print("[Worker] !!! 仿真发生错误 !!!")
                result["status"] = "failed"
                result["diagnostics"]["error_msg"] = sim_capture["error_report"] or "MATLAB 仿真失败"
                return result

            print("[Worker] 正在提取 KPI 指标...")
            try:
                overshoot = self.eng.eval("max(Speed_Feedback) - Target_Speed", nargout=1)
                result["kpi"] = {
                    "overshoot_raw": overshoot,
                    "status_code": 1,
                }
            except Exception as kpi_err:
                print(f"[Worker] 警告: 提取 KPI 失败，可能是变量不存在。({kpi_err})")
                result["diagnostics"]["kpi_error_msg"] = str(kpi_err)

            result["outputs"] = self._collect_result_vars(result_vars)
            result["status"] = "done"

            return result

        except matlab.engine.MatlabExecutionError as e:
            print("[Worker] !!! 仿真发生错误 !!!")
            result["status"] = "failed"
            result["diagnostics"]["error_msg"] = str(e)
            return result

        except Exception as ex:
            print(f"[Worker] !!! 未知异常 !!!: {ex}")
            result["status"] = "failed"
            result["diagnostics"]["error_msg"] = str(ex)
            return result
