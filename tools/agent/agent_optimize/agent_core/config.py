import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


@dataclass
class ProjectContext:
    app_dir: Path
    env_path: Path
    project_config_path: Path
    project_config_dir: Path
    config: Dict[str, Any]

    def resolve_config_path(self, raw_path: str) -> Path:
        """Resolve a path relative to agent_project.json."""
        path = Path(raw_path).expanduser()
        if not path.is_absolute():
            path = self.project_config_dir / path
        return path.resolve()

    def automation(self) -> Dict[str, Any]:
        return self.config.get("automation", {})

    def resources(self) -> Dict[str, Dict[str, Any]]:
        raw_resources = self.config.get("resources") or self.config.get("files") or {}
        normalized: Dict[str, Dict[str, Any]] = {}

        for key, value in raw_resources.items():
            if isinstance(value, str):
                item = {"path": value}
            elif isinstance(value, dict):
                item = dict(value)
            else:
                continue

            raw_path = item.get("path")
            if not raw_path:
                continue

            path = self.resolve_config_path(raw_path)
            resource_type = item.get("type")
            if resource_type not in {"file", "directory"}:
                if path.exists() and path.is_dir():
                    resource_type = "directory"
                else:
                    resource_type = "file"

            item["path"] = str(path)
            item["type"] = resource_type
            normalized[key] = item

        return normalized

    def get_resource(self, resource_key: str) -> Tuple[Optional[Dict[str, Any]], str]:
        resources = self.resources()
        if resource_key not in resources:
            available = ", ".join(resources.keys()) or "none"
            return None, f"Error: unknown resource_key: {resource_key}. Available keys: {available}"
        return resources[resource_key], ""


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(
            f"Project config file was not found: {path}\n"
            "Please create agent_project.json beside agent_modified.py, or set AGENT_PROJECT_CONFIG."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in project config: {path}\n{exc}") from exc


def load_project_context() -> ProjectContext:
    # agent_core/config.py -> agent_core -> app folder
    app_dir = Path(__file__).resolve().parents[1]
    env_path = app_dir / ".env"
    project_config_path = Path(
        os.getenv("AGENT_PROJECT_CONFIG", str(app_dir / "agent_project.json"))
    ).expanduser().resolve()
    config = _load_json(project_config_path)
    return ProjectContext(
        app_dir=app_dir,
        env_path=env_path,
        project_config_path=project_config_path,
        project_config_dir=project_config_path.parent,
        config=config,
    )
