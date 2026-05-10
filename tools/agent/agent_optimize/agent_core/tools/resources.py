import json

from pathlib import Path
from typing import Any, Dict

from ..config import ProjectContext
from ..constants import DEFAULT_ALLOWED_EXTENSIONS, DEFAULT_MAX_CHARS, DEFAULT_MAX_DIR_ENTRIES
from ..tool_registry import ToolRegistry
from ..utils import is_inside, read_text_file, truncate_text

SIMULATION_RESULT_RESOURCE_KEYS = {"simulation_result"}
LARGE_SIMULATION_FILE_NAMES = {"processed.json", "raw.json"}
SIMULATION_RESULT_MAX_READ_CHARS = 8000

class ResourceTools:
    def __init__(self, ctx: ProjectContext) -> None:
        self.ctx = ctx

    def _extension_allowed(self, path: Path, item: Dict[str, Any]) -> bool:
        allowed = item.get("allowed_extensions")
        if allowed is None:
            allowed_set = DEFAULT_ALLOWED_EXTENSIONS
        else:
            allowed_set = {str(ext).lower() for ext in allowed}
        if "*" in allowed_set:
            return True
        return path.suffix.lower() in allowed_set

    def list_project_resources(self) -> str:
        resources = self.ctx.resources()
        if not resources:
            return "No resources are configured in agent_project.json."

        lines = []
        project_name = self.ctx.config.get("project_name", "unnamed_project")
        lines.append(f"Project: {project_name}")
        lines.append(f"Config: {self.ctx.project_config_path}")
        lines.append("Allowed resources:")

        for key, item in resources.items():
            path = Path(item["path"])
            exists = path.exists()
            resource_type = item.get("type", "file")
            description = item.get("description", "")
            status = "exists" if exists else "missing"
            lines.append(f"- {key}")
            lines.append(f"  type: {resource_type}")
            lines.append(f"  status: {status}")
            lines.append(f"  path: {path}")
            if description:
                lines.append(f"  description: {description}")
        return "\n".join(lines)

    def list_directory(
        self,
        resource_key: str,
        relative_dir: str = "",
        max_entries: int = DEFAULT_MAX_DIR_ENTRIES,
    ) -> str:
        item, err = self.ctx.get_resource(resource_key)
        if err:
            return err
        assert item is not None

        if item.get("type") != "directory":
            return f"Error: resource_key={resource_key} is not a directory resource."

        base_path = Path(item["path"]).resolve()
        if not base_path.exists():
            return f"Error: directory does not exist: {base_path}"
        if not base_path.is_dir():
            return f"Error: configured path is not a directory: {base_path}"

        target_dir = (base_path / relative_dir).resolve()
        if not is_inside(target_dir, base_path):
            return "Error: forbidden path traversal outside the configured directory."
        if not target_dir.exists():
            return f"Error: directory does not exist: {target_dir}"
        if not target_dir.is_dir():
            return f"Error: path is not a directory: {target_dir}"

        entries = sorted(target_dir.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        limited = entries[:max_entries]

        lines = [
            f"Directory resource: {resource_key}",
            f"Base path: {base_path}",
            f"Current dir: {target_dir}",
            "Entries:",
        ]

        for entry in limited:
            kind = "dir" if entry.is_dir() else "file"
            rel = entry.relative_to(base_path)
            size = ""
            if entry.is_file():
                try:
                    size = f", {entry.stat().st_size} bytes"
                except OSError:
                    size = ""
            lines.append(f"- [{kind}] {rel}{size}")

        if len(entries) > max_entries:
            lines.append(f"[TRUNCATED: {len(entries)} entries total, returned first {max_entries}.]")
        return "\n".join(lines)

    def list_simulation_signals(
        self,
        resource_key: str = "simulation_result",
        relative_path: str = "",
        max_signals: int = 200,
    ) -> str:
        """
        List available signal names and lightweight metadata from processed.json.

        This tool intentionally does not return raw time-series values.
        It is intended for the agent to inspect signal names before creating
        evaluation_config.json.
        """
        item, err = self.ctx.get_resource(resource_key)
        if err:
            return err
        assert item is not None

        resource_type = item.get("type", "file")
        base_path = Path(item["path"]).resolve()

        if resource_type == "file":
            if relative_path:
                return (
                    f"Error: resource_key={resource_key} is a file resource. "
                    "Do not provide relative_path."
                )
            target = base_path
        elif resource_type == "directory":
            if not relative_path:
                return (
                    f"Error: resource_key={resource_key} is a directory. "
                    "Please provide relative_path, for example processed.json."
                )
            target = (base_path / relative_path).resolve()
            if not is_inside(target, base_path):
                return "Error: forbidden path traversal outside the configured directory."
        else:
            return f"Error: unsupported resource type: {resource_type}"

        if not target.exists():
            return f"Error: file does not exist: {target}"
        if not target.is_file():
            return f"Error: path is not a file: {target}"

        if resource_type == "directory" and not self._extension_allowed(target, item):
            return (
                f"Error: file extension is not allowed for this directory resource: {target.suffix}\n"
                "If this file is safe to read, add it to allowed_extensions in agent_project.json."
            )

        if target.name.lower() not in LARGE_SIMULATION_FILE_NAMES:
            return (
                f"Error: list_simulation_signals is intended for processed.json/raw.json only. "
                f"Got: {target.name}"
            )

        try:
            data = json.loads(read_text_file(target))
        except json.JSONDecodeError as exc:
            return f"Error: failed to parse JSON file: {target}\n{exc}"

        signals = data.get("signals")
        if not isinstance(signals, dict):
            return (
                f"Error: JSON file does not contain a valid 'signals' object: {target}\n"
                "Expected processed.json format: {'signals': {signal_name: {'time': [...], 'values': [...]}}}"
            )

        signal_items = list(signals.items())
        limited_items = signal_items[:max_signals]

        result: Dict[str, Any] = {
            "file": str(target),
            "status": data.get("status"),
            "signal_count": len(signal_items),
            "returned_signal_count": len(limited_items),
            "signals": [],
            "note": (
                "This tool returns signal names and metadata only. "
                "It does not return raw time-series values. "
                "Use evaluate_simulation_result to compute performance metrics."
            ),
        }

        for name, payload in limited_items:
            if not isinstance(payload, dict):
                result["signals"].append(
                    {
                        "name": name,
                        "error": "signal payload is not an object",
                    }
                )
                continue

            time_values = payload.get("time", [])
            values = payload.get("values", [])

            sample_count = None
            time_start = None
            time_end = None

            if isinstance(time_values, list):
                sample_count = len(time_values)
                if time_values:
                    time_start = time_values[0]
                    time_end = time_values[-1]
            elif isinstance(values, list):
                sample_count = len(values)

            result["signals"].append(
                {
                    "name": name,
                    "source_scope": payload.get("source_scope"),
                    "source_channel": payload.get("source_channel"),
                    "sample_count": sample_count,
                    "time_start": time_start,
                    "time_end": time_end,
                }
            )

        if len(signal_items) > max_signals:
            result["truncated"] = True
            result["message"] = (
                f"Returned first {max_signals} signals out of {len(signal_items)} total."
            )
        else:
            result["truncated"] = False

        return json.dumps(result, ensure_ascii=False, indent=2)


    def read_project_file(
        self,
        resource_key: str,
        relative_path: str = "",
        max_chars: int = DEFAULT_MAX_CHARS,
    ) -> str:
        item, err = self.ctx.get_resource(resource_key)
        if err:
            return err
        assert item is not None

        resource_type = item.get("type", "file")
        base_path = Path(item["path"]).resolve()

        if resource_type == "file":
            if relative_path:
                return f"Error: resource_key={resource_key} is a file resource. Do not provide relative_path."
            target = base_path
        elif resource_type == "directory":
            if not relative_path:
                return f"Error: resource_key={resource_key} is a directory. Please provide relative_path, or call list_directory first."
            target = (base_path / relative_path).resolve()
            if not is_inside(target, base_path):
                return "Error: forbidden path traversal outside the configured directory."
        else:
            return f"Error: unsupported resource type: {resource_type}"

        if not target.exists():
            return f"Error: file does not exist: {target}"
        if not target.is_file():
            return f"Error: path is not a file: {target}"
        if resource_type == "directory" and not self._extension_allowed(target, item):
            return (
                f"Error: file extension is not allowed for this directory resource: {target.suffix}\n"
                "If this file is safe to read, add it to allowed_extensions in agent_project.json."
            )

        if (
            resource_key in SIMULATION_RESULT_RESOURCE_KEYS
            or target.name.lower() in LARGE_SIMULATION_FILE_NAMES
        ):
            if max_chars > SIMULATION_RESULT_MAX_READ_CHARS:
                return (
                    "Error: reading large simulation result files is restricted.\n"
                    f"Requested max_chars={max_chars}, allowed max_chars<={SIMULATION_RESULT_MAX_READ_CHARS}.\n"
                    "Use list_simulation_signals to inspect available signal names.\n"
                    "Use write_evaluation_config and evaluate_simulation_result to compute performance metrics.\n"
                    "Do not read full processed.json/raw.json or raw time-series values through read_project_file."
                )
        content = truncate_text(read_text_file(target), max_chars)
        return f"[FILE: {target}]\n\n{content}"


def register_resource_tools(registry: ToolRegistry, ctx: ProjectContext) -> ResourceTools:
    tool = ResourceTools(ctx)

    registry.register(
        "list_simulation_signals",
        {
            "type": "function",
            "function": {
                "name": "list_simulation_signals",
                "description": (
                    "List available signal names and lightweight metadata from processed.json "
                    "without returning raw time-series values. Use this before creating "
                    "evaluation_config.json. Do not use read_project_file to inspect full "
                    "processed.json values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_key": {
                            "type": "string",
                            "description": (
                                "Resource key in agent_project.json. "
                                "Default is simulation_result."
                            ),
                        },
                        "relative_path": {
                            "type": "string",
                            "description": (
                                "Only needed when resource_key points to a directory. "
                                "For example: processed.json."
                            ),
                        },
                        "max_signals": {
                            "type": "integer",
                            "description": "Maximum number of signal entries to return.",
                        },
                    },
                },
            },
        },
        lambda args: tool.list_simulation_signals(
            resource_key=args.get("resource_key", "simulation_result"),
            relative_path=args.get("relative_path", ""),
            max_signals=args.get("max_signals", 200),
        ),
    )

    registry.register(
        "list_project_resources",
        {
            "type": "function",
            "function": {
                "name": "list_project_resources",
                "description": "List all configured project resources that the agent is allowed to access.",
                "parameters": {"type": "object", "properties": {}},
            },
        },
        lambda args: tool.list_project_resources(),
    )

    registry.register(
        "list_directory",
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List files under a configured directory resource. Use this before reading a file from a directory resource.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_key": {"type": "string", "description": "Configured directory key, for example project_src."},
                        "relative_dir": {"type": "string", "description": "Optional subdirectory path relative to the configured directory."},
                        "max_entries": {"type": "integer", "description": "Maximum number of directory entries to return."},
                    },
                    "required": ["resource_key"],
                },
            },
        },
        lambda args: tool.list_directory(
            resource_key=args["resource_key"],
            relative_dir=args.get("relative_dir", ""),
            max_entries=args.get("max_entries", DEFAULT_MAX_DIR_ENTRIES),
        ),
    )

    registry.register(
        "read_project_file",
        {
            "type": "function",
            "function": {
                "name": "read_project_file",
                "description": (
                     "Read a configured small text file resource, or read a file inside a configured directory resource. "
                     "Do not use this tool to inspect full processed.json/raw.json time-series data. "
                     "For simulation signal names use list_simulation_signals. "
                     "For performance metrics use evaluate_simulation_result."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "resource_key": {"type": "string", "description": "Resource key in agent_project.json."},
                        "relative_path": {"type": "string", "description": "Only needed when resource_key points to a directory."},
                        "max_chars": {"type": "integer", "description": "Maximum characters to return. Default is 20000."},
                    },
                    "required": ["resource_key"],
                },
            },
        },
        lambda args: tool.read_project_file(
            resource_key=args["resource_key"],
            relative_path=args.get("relative_path", ""),
            max_chars=args.get("max_chars", DEFAULT_MAX_CHARS),
        ),
    )

    return tool
