"""
parameter_edit.py

Agent tool adapters for editing the lightweight GMP tunable-parameter header.

This module exposes three LLM-callable tools:
1. read_tunable_parameters
2. patch_tunable_parameters
3. restore_tunable_parameters_backup

It is designed to work with agent_core/parameters/parameter_header_editor.py,
where the current generated header file itself acts as the per-control-structure
allow-list. Different control structures may expose different parameter names;
the agent should therefore call read_tunable_parameters first and only patch
parameters returned by that tool.

Python version: 3.10+
Dependencies: standard library only
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional
import json

from ..config import ProjectContext
from ..parameters.parameter_header_editor import (
    ParameterHeaderError,
    patch_tunable_parameters as patch_header_parameters,
    read_tunable_parameters as read_header_parameters,
    read_tunable_parameters_detailed,
    restore_header_backup,
)
from ..tool_registry import ToolRegistry


class ParameterEditTools:
    """Tool-call wrapper around the lightweight parameter header editor."""

    # Automation/resource keys accepted as default locations. This keeps the
    # tool usable both with explicit user-provided paths and later project config
    # integration, without forcing a manifest file.
    HEADER_PATH_KEYS = (
        "parameter_header",
        "tunable_parameter_header",
        "tunable_params_header",
        "paras_header",
        "paras_generated_header",
    )

    def __init__(self, ctx: ProjectContext) -> None:
        self.ctx = ctx

    def _automation(self) -> Dict[str, Any]:
        return self.ctx.automation()

    def _resolve_optional_path(self, raw_path: Optional[str], *, purpose: str) -> Path:
        """
        Resolve a path supplied to a tool.

        If raw_path is empty, try known keys from agent_project.json automation
        and resources sections. This allows future config-only use while keeping
        the current workflow simple: pass header_path directly.
        """
        if isinstance(raw_path, str) and raw_path.strip():
            return self.ctx.resolve_config_path(raw_path.strip())

        for key in self.HEADER_PATH_KEYS:
            value = self._automation().get(key)
            if isinstance(value, str) and value.strip():
                return self.ctx.resolve_config_path(value.strip())

        resources = self.ctx.resources()
        for key in self.HEADER_PATH_KEYS:
            item = resources.get(key)
            if isinstance(item, dict):
                value = item.get("path")
                if isinstance(value, str) and value.strip():
                    return Path(value).expanduser().resolve()

        accepted = ", ".join(self.HEADER_PATH_KEYS)
        raise ValueError(
            f"Missing {purpose}. Provide argument 'header_path', or configure one of these "
            f"agent_project.json automation/resources keys: {accepted}."
        )

    def _resolve_backup_dir(self, raw_path: Optional[str]) -> Optional[Path]:
        if isinstance(raw_path, str) and raw_path.strip():
            return self.ctx.resolve_config_path(raw_path.strip())
        return None

    @staticmethod
    def _normalize_allowed_names(raw: Any) -> Optional[Iterable[str]]:
        if raw is None:
            return None
        if isinstance(raw, str):
            stripped = raw.strip()
            if not stripped:
                return None
            return [item.strip() for item in stripped.split(",") if item.strip()]
        if isinstance(raw, list):
            names = []
            for item in raw:
                if not isinstance(item, str) or not item.strip():
                    raise ValueError("allowed_names must contain only non-empty strings.")
                names.append(item.strip())
            return names or None
        raise ValueError("allowed_names must be a list of strings, a comma-separated string, or null.")

    @staticmethod
    def _to_pretty_json(data: Mapping[str, Any]) -> str:
        return json.dumps(data, ensure_ascii=False, indent=2)

    def read_tunable_parameters(
        self,
        *,
        header_path: Optional[str] = None,
        include_details: bool = False,
        allowed_names: Any = None,
        require_markers: bool = True,
    ) -> str:
        """
        Read available tunable parameters from paras.generated.h or equivalent.

        The returned parameter names are the safe patchable set for the current
        control structure.
        """
        try:
            path = self._resolve_optional_path(header_path, purpose="parameter header path")
            allowed = self._normalize_allowed_names(allowed_names)

            if include_details:
                detailed = read_tunable_parameters_detailed(
                    path,
                    allowed_names=allowed,
                    require_markers=require_markers,
                )
                parameters = {name: item.value for name, item in detailed.items()}
                result: Dict[str, Any] = {
                    "status": "ok",
                    "header_path": str(path),
                    "parameter_count": len(parameters),
                    "parameters": parameters,
                    "details": {name: item.to_dict() for name, item in detailed.items()},
                    "note": (
                        "These names are the currently available tunable parameters. "
                        "Patch only names listed here."
                    ),
                }
            else:
                parameters = read_header_parameters(
                    path,
                    allowed_names=allowed,
                    require_markers=require_markers,
                )
                result = {
                    "status": "ok",
                    "header_path": str(path),
                    "parameter_count": len(parameters),
                    "parameters": parameters,
                    "available_parameter_names": sorted(parameters.keys()),
                    "note": (
                        "These names are the currently available tunable parameters. "
                        "Different control structures may expose different names. "
                        "Patch only names listed here."
                    ),
                }
        except (ParameterHeaderError, OSError, TypeError, ValueError) as exc:
            return f"Error: failed to read tunable parameters. {type(exc).__name__}: {exc}"

        return self._to_pretty_json(result)

    def patch_tunable_parameters(
        self,
        *,
        updates: Mapping[str, Any],
        header_path: Optional[str] = None,
        backup: bool = True,
        backup_dir: Optional[str] = None,
        allowed_names: Any = None,
        require_markers: bool = True,
        dry_run: bool = False,
    ) -> str:
        """
        Patch existing tunable parameters in the generated header.

        The tool rejects unknown parameter names. It never adds new parameters
        and never lets the LLM directly rewrite the header file.
        """
        if not isinstance(updates, Mapping):
            return (
                "Error: patch_tunable_parameters expects argument 'updates' to be an object/dict, "
                f"got {type(updates).__name__}."
            )

        try:
            path = self._resolve_optional_path(header_path, purpose="parameter header path")
            backup_root = self._resolve_backup_dir(backup_dir)
            allowed = self._normalize_allowed_names(allowed_names)

            before = read_header_parameters(
                path,
                allowed_names=allowed,
                require_markers=require_markers,
            )
            patch_result = patch_header_parameters(
                path,
                updates,
                backup=backup,
                backup_dir=backup_root,
                allowed_names=allowed,
                require_markers=require_markers,
                dry_run=dry_run,
            )
            after = read_header_parameters(
                path,
                allowed_names=allowed,
                require_markers=require_markers,
            )

            updated_names = sorted((patch_result.get("updated_parameters") or {}).keys())
            result = {
                "status": "ok",
                "dry_run": dry_run,
                "changed": patch_result.get("changed", False),
                "header_path": str(path),
                "backup_file": patch_result.get("backup_file"),
                "updated_parameter_names": updated_names,
                "before": {name: before.get(name) for name in updated_names},
                "after": {name: after.get(name) for name in updated_names},
                "available_parameter_names": patch_result.get("available_parameters", sorted(after.keys())),
                "patch_detail": patch_result.get("updated_parameters", {}),
                "note": (
                    "Patch applied only to existing numeric parameters inside the tunable block. "
                    "Run build/simulation/evaluation again to judge whether the update improved performance."
                ),
            }
        except (ParameterHeaderError, OSError, TypeError, ValueError) as exc:
            return f"Error: failed to patch tunable parameters. {type(exc).__name__}: {exc}"

        return self._to_pretty_json(result)

    def restore_tunable_parameters_backup(
        self,
        *,
        header_path: Optional[str] = None,
        backup_file: Optional[str] = None,
        backup_dir: Optional[str] = None,
    ) -> str:
        """Restore the parameter header from a specific or latest backup file."""
        try:
            path = self._resolve_optional_path(header_path, purpose="parameter header path")
            backup_root = self._resolve_backup_dir(backup_dir)
            backup_path = self.ctx.resolve_config_path(backup_file.strip()) if isinstance(backup_file, str) and backup_file.strip() else None

            result = restore_header_backup(
                path,
                backup_file=backup_path,
                backup_dir=backup_root,
            )
        except (ParameterHeaderError, OSError, TypeError, ValueError) as exc:
            return f"Error: failed to restore tunable parameter backup. {type(exc).__name__}: {exc}"

        return self._to_pretty_json(result)


def register_parameter_edit_tools(registry: ToolRegistry, ctx: ProjectContext) -> ParameterEditTools:
    tool = ParameterEditTools(ctx)

    registry.register(
        "read_tunable_parameters",
        {
            "type": "function",
            "function": {
                "name": "read_tunable_parameters",
                "description": (
                    "Read available tunable control parameters from the generated parameter header. "
                    "Use this before deciding parameter updates, because different control structures "
                    "may expose different parameter names."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "header_path": {
                            "type": "string",
                            "description": (
                                "Path to paras.generated.h or equivalent. Can be absolute or relative to agent_project.json. "
                                "Required unless a parameter header path is configured in agent_project.json."
                            ),
                        },
                        "include_details": {
                            "type": "boolean",
                            "description": "Optional. Default false. Include source line, raw literal, and declaration kind.",
                        },
                        "allowed_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional extra allow-list. Usually omit this so the current header file determines "
                                "the allowed parameter names."
                            ),
                        },
                        "require_markers": {
                            "type": "boolean",
                            "description": "Optional. Default true. Only parse the marked tunable block.",
                        },
                    },
                },
            },
        },
        lambda args: tool.read_tunable_parameters(
            header_path=args.get("header_path"),
            include_details=bool(args.get("include_details", False)),
            allowed_names=args.get("allowed_names"),
            require_markers=bool(args.get("require_markers", True)),
        ),
    )

    registry.register(
        "patch_tunable_parameters",
        {
            "type": "function",
            "function": {
                "name": "patch_tunable_parameters",
                "description": (
                    "Patch existing numeric tunable parameters in the generated parameter header. "
                    "Call read_tunable_parameters first and only update names returned by that tool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "header_path": {
                            "type": "string",
                            "description": (
                                "Path to paras.generated.h or equivalent. Can be absolute or relative to agent_project.json. "
                                "Required unless a parameter header path is configured in agent_project.json."
                            ),
                        },
                        "updates": {
                            "type": "object",
                            "description": (
                                "Mapping from existing parameter name to new numeric value. Example: "
                                "{\"VEL_KP\": 4.5, \"CUR_LIMIT\": 0.25}."
                            ),
                        },
                        "backup": {
                            "type": "boolean",
                            "description": "Optional. Default true. Create a timestamped backup before writing.",
                        },
                        "backup_dir": {
                            "type": "string",
                            "description": "Optional backup directory, absolute or relative to agent_project.json.",
                        },
                        "allowed_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Optional extra allow-list. Usually omit this so the current header file determines "
                                "the allowed parameter names."
                            ),
                        },
                        "require_markers": {
                            "type": "boolean",
                            "description": "Optional. Default true. Only patch the marked tunable block.",
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "Optional. Default false. If true, return planned patch without writing the file.",
                        },
                    },
                    "required": ["updates"],
                },
            },
        },
        lambda args: tool.patch_tunable_parameters(
            header_path=args.get("header_path"),
            updates=args["updates"],
            backup=bool(args.get("backup", True)),
            backup_dir=args.get("backup_dir"),
            allowed_names=args.get("allowed_names"),
            require_markers=bool(args.get("require_markers", True)),
            dry_run=bool(args.get("dry_run", False)),
        ),
    )

    registry.register(
        "restore_tunable_parameters_backup",
        {
            "type": "function",
            "function": {
                "name": "restore_tunable_parameters_backup",
                "description": (
                    "Restore the generated parameter header from a specific backup file, or from the latest "
                    "timestamped backup if backup_file is omitted."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "header_path": {
                            "type": "string",
                            "description": (
                                "Path to paras.generated.h or equivalent. Can be absolute or relative to agent_project.json. "
                                "Required unless a parameter header path is configured in agent_project.json."
                            ),
                        },
                        "backup_file": {
                            "type": "string",
                            "description": (
                                "Optional exact backup file to restore. If omitted, the latest matching backup is used."
                            ),
                        },
                        "backup_dir": {
                            "type": "string",
                            "description": "Optional backup directory, absolute or relative to agent_project.json.",
                        },
                    },
                },
            },
        },
        lambda args: tool.restore_tunable_parameters_backup(
            header_path=args.get("header_path"),
            backup_file=args.get("backup_file"),
            backup_dir=args.get("backup_dir"),
        ),
    )

    return tool


__all__ = ["ParameterEditTools", "register_parameter_edit_tools"]
