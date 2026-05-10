import subprocess
import time
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import ProjectContext
from ..constants import DEFAULT_MAX_CHARS
from ..process_runner import run_bat_sync_in_new_console, start_bat_async
from ..tool_registry import ToolRegistry
from ..utils import file_updated_after, read_text_if_exists


class AutomationTools:
    def __init__(self, ctx: ProjectContext) -> None:
        self.ctx = ctx
        self.active_exe_process: Optional[subprocess.Popen] = None
        self.active_exe_started_at: float = 0.0
        self.active_exe_bat_path: Optional[Path] = None

    def _automation(self) -> Dict[str, Any]:
        return self.ctx.automation()

    def _path_from_automation(self, key: str, default: Optional[str] = None) -> Optional[Path]:
        value = self._automation().get(key, default)
        if not value:
            return None
        return self.ctx.resolve_config_path(str(value))

    def build_solution(self) -> str:
        """Run build_sln.bat synchronously. With the split-bat design, this bat must only build and exit."""
        automation = self._automation()
        bat_path = self._path_from_automation("build_bat_path")
        if bat_path is None:
            return "Error: automation.build_bat_path is not configured in agent_project.json."

        timeout_sec = int(automation.get("build_timeout_sec", 900))
        build_log = self._path_from_automation("build_agent_log", "../log/build.log")
        started_at = time.time()

        result = run_bat_sync_in_new_console(
            bat_path=bat_path,
            args=[],
            timeout_sec=timeout_sec,
        )

        log_status = ""
        if build_log is not None:
            if file_updated_after(build_log, started_at, slack_sec=2.0):
                log_status = f"build.log was updated: {build_log}"
            elif build_log.exists():
                log_status = f"build.log exists but timestamp does not look newer than this run: {build_log}"
            else:
                log_status = f"build.log does not exist: {build_log}"

        if result.startswith("Error"):
            return (
                "Error: build_sln.bat failed.\n\n"
                f"[bat_result]\n{result}\n\n"
                f"[build_log_status]\n{log_status}\n\n"
                f"[build.log]\n{read_text_if_exists(build_log, DEFAULT_MAX_CHARS) if build_log else '[not configured]'}"
            )

        return (
            "OK: build stage finished successfully.\n\n"
            f"[bat_result]\n{result}\n\n"
            f"[build_log_status]\n{log_status}\n\n"
            f"[build.log]\n{read_text_if_exists(build_log, 4000) if build_log else '[not configured]'}"
        )

    def start_exe(self) -> str:
        """Start start_exe.bat asynchronously. The exe may block while waiting for Simulink."""
        automation = self._automation()
        bat_path = self._path_from_automation("start_exe_bat_path")
        if bat_path is None:
            return "Error: automation.start_exe_bat_path is not configured in agent_project.json."

        if self.active_exe_process is not None and self.active_exe_process.poll() is None:
            return (
                "Error: an exe/start_exe process is already running. "
                f"pid={self.active_exe_process.pid}. Wait for it to finish before starting another run."
            )

        run_exe_log = self._path_from_automation("run_exe_log", "../log/run_exe.log")
        timeout_sec = int(automation.get("exe_start_timeout_sec", 120))

        started_at = time.time()
        proc, msg = start_bat_async(bat_path=bat_path, args=[], new_console=True)
        if proc is None:
            return msg

        self.active_exe_process = proc
        self.active_exe_started_at = started_at
        self.active_exe_bat_path = bat_path

        # Wait for run_exe.log to update. This confirms start_exe.bat reached the exe-launch stage.
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            if run_exe_log is not None and file_updated_after(run_exe_log, started_at, slack_sec=1.0):
                return (
                    f"{msg}\n"
                    "OK: exe launch was observed via run_exe.log update. The exe may now be waiting for Simulink.\n\n"
                    f"[run_exe.log]\n{read_text_if_exists(run_exe_log, 4000)}"
                )

            returncode = proc.poll()
            if returncode is not None:
                if returncode == 0:
                    return (
                        f"{msg}\n"
                        "OK: start_exe.bat exited quickly with code 0 before run_exe.log update. "
                        "This may mean the exe finished very quickly.\n\n"
                        f"[run_exe.log]\n{read_text_if_exists(run_exe_log, 4000) if run_exe_log else '[not configured]'}"
                    )
                return (
                    f"Error: start_exe.bat exited before exe launch. returncode={returncode}\n\n"
                    f"[run_exe.log]\n{read_text_if_exists(run_exe_log, DEFAULT_MAX_CHARS) if run_exe_log else '[not configured]'}"
                )
            time.sleep(0.5)

        return (
            f"Error: timed out while waiting for run_exe.log update after {timeout_sec} seconds.\n"
            f"pid={proc.pid}, bat={bat_path}\n\n"
            f"[run_exe.log]\n{read_text_if_exists(run_exe_log, DEFAULT_MAX_CHARS) if run_exe_log else '[not configured]'}"
        )

    def run_simulation_bat(self) -> str:
        """Run run_local_quick.bat synchronously. It should finish after Simulink writes processed.json."""
        automation = self._automation()
        bat_path = self._path_from_automation("sim_bat_path")
        if bat_path is None:
            return "Error: automation.sim_bat_path is not configured in agent_project.json."

        timeout_sec = int(automation.get("sim_timeout_sec", 1800))
        result_json = self._path_from_automation("simulation_result", "../log/processed.json")
        run_exe_log = self._path_from_automation("run_exe_log", "../log/run_exe.log")

        args = []
        model_path = self._path_from_automation("sim_model_path")
        if model_path is not None:
            args.append(str(model_path))

        sim_started_at = time.time()
        sim_result = run_bat_sync_in_new_console(
            bat_path=bat_path,
            args=args,
            timeout_sec=timeout_sec,
        )

        result_status = ""
        if result_json is not None:
            if file_updated_after(result_json, sim_started_at, slack_sec=3.0):
                result_status = f"processed.json was updated: {result_json}"
            elif result_json.exists():
                result_status = f"processed.json exists but timestamp does not look newer than this run: {result_json}"
            else:
                result_status = f"processed.json does not exist: {result_json}"

        parts = [
            sim_result,
            result_status,
            "",
            f"[run_exe.log]\n{read_text_if_exists(run_exe_log, 4000) if run_exe_log else '[not configured]'}",
        ]
        return "\n".join(parts)

    def wait_for_exe_exit(self, timeout_sec: int = 120) -> str:
        if self.active_exe_process is None:
            return "OK: no active exe/start_exe process is tracked."

        try:
            code = self.active_exe_process.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            return (
                "Warning: start_exe.bat/exe did not exit within "
                f"{timeout_sec} seconds. pid={self.active_exe_process.pid}. "
                "Check whether the exe is still waiting or stuck."
            )

        pid = self.active_exe_process.pid
        self.active_exe_process = None
        return f"OK: start_exe.bat/exe exited. pid={pid}, returncode={code}."

    def run_closed_loop_once(self) -> str:
        """One complete split-bat orchestration."""
        build_result = self.build_solution()
        if build_result.lstrip().startswith("Error:"):
            return "Closed loop stopped at build stage.\n\n" + build_result

        exe_result = self.start_exe()
        if exe_result.lstrip().startswith("Error:"):
            return (
                "Closed loop stopped at exe-start stage.\n\n"
                f"[build_result]\n{build_result}\n\n"
                f"[exe_result]\n{exe_result}"
            )

        sim_result = self.run_simulation_bat()
        if sim_result.lstrip().startswith("Error:"):
            wait_result = self.wait_for_exe_exit(timeout_sec=30)
            return (
                "Closed loop stopped at simulation stage.\n\n"
                f"[build_result]\n{build_result}\n\n"
                f"[exe_result]\n{exe_result}\n\n"
                f"[simulation_result]\n{sim_result}\n\n"
                f"[wait_for_exe_exit]\n{wait_result}"
            )

        wait_result = self.wait_for_exe_exit(timeout_sec=120)

        result_json = self._path_from_automation("simulation_result", "../log/processed.json")
        run_exe_log = self._path_from_automation("run_exe_log", "../log/run_exe.log")

        return (
            "OK: closed-loop run finished.\n\n"
            f"[build_result]\n{build_result}\n\n"
            f"[exe_result]\n{exe_result}\n\n"
            f"[simulation_result]\n{sim_result}\n\n"
            f"[wait_for_exe_exit]\n{wait_result}\n\n"
            f"[processed.json]\n{read_text_if_exists(result_json, 4000) if result_json else '[not configured]'}\n\n"
            f"[run_exe.log]\n{read_text_if_exists(run_exe_log, 4000) if run_exe_log else '[not configured]'}"
        )


def register_automation_tools(registry: ToolRegistry, ctx: ProjectContext) -> AutomationTools:
    tool = AutomationTools(ctx)

    registry.register(
        "build_solution",
        {
            "type": "function",
            "function": {
                "name": "build_solution",
                "description": "Synchronously call build_sln.bat to build the Visual Studio solution. Split-bat version: this bat must only build and exit.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        lambda args: tool.build_solution(),
    )

    registry.register(
        "start_exe",
        {
            "type": "function",
            "function": {
                "name": "start_exe",
                "description": "Asynchronously call start_exe.bat to start the generated exe. The exe may wait for Simulink.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        lambda args: tool.start_exe(),
    )

    registry.register(
        "run_simulation_bat",
        {
            "type": "function",
            "function": {
                "name": "run_simulation_bat",
                "description": "Synchronously call run_local_quick.bat to run the Simulink simulation and generate processed.json.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        lambda args: tool.run_simulation_bat(),
    )

    registry.register(
        "wait_for_exe_exit",
        {
            "type": "function",
            "function": {
                "name": "wait_for_exe_exit",
                "description": "Wait for the active start_exe.bat/exe process to exit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "timeout_sec": {"type": "integer", "description": "Seconds to wait. Default is 120."}
                    },
                },
            },
        },
        lambda args: tool.wait_for_exe_exit(timeout_sec=args.get("timeout_sec", 120)),
    )

    registry.register(
        "run_closed_loop_once",
        {
            "type": "function",
            "function": {
                "name": "run_closed_loop_once",
                "description": "Run one complete split-bat closed loop: build_sln.bat, start_exe.bat, run_local_quick.bat, wait for exe exit, then report processed.json and run_exe.log.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        lambda args: tool.run_closed_loop_once(),
    )

    return tool
