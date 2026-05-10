import os
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple


def validate_bat_path(bat_path: Path) -> Optional[str]:
    if os.name != "nt":
        return "Error: .bat execution requires Windows. This tool must be run on the engineering PC."
    if not bat_path.exists():
        return f"Error: bat file does not exist: {bat_path}"
    if bat_path.suffix.lower() != ".bat":
        return f"Error: configured automation target is not a .bat file: {bat_path}"
    return None


def start_bat_async(
    bat_path: Path,
    args: Optional[List[str]] = None,
    new_console: bool = True,
) -> Tuple[Optional[subprocess.Popen], str]:
    """Start a whitelisted .bat asynchronously. No arbitrary command strings."""
    err = validate_bat_path(bat_path)
    if err:
        return None, err

    command = ["cmd.exe", "/d", "/c", str(bat_path)]
    if args:
        command.extend(str(arg) for arg in args)

    creationflags = 0
    if new_console:
        creationflags |= getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    else:
        creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    try:
        proc = subprocess.Popen(
            command,
            cwd=str(bat_path.parent),
            creationflags=creationflags,
        )
    except OSError as exc:
        return None, f"Error: failed to start bat file: {bat_path}\n{exc}"

    return proc, f"OK: started bat asynchronously. pid={proc.pid}, bat={bat_path}"


def run_bat_sync_in_new_console(
    bat_path: Path,
    args: Optional[List[str]] = None,
    timeout_sec: int = 600,
) -> str:
    """Start a whitelisted .bat in a new console and wait for it."""
    proc, msg = start_bat_async(bat_path=bat_path, args=args, new_console=True)
    if proc is None:
        return msg

    try:
        returncode = proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        return f"Error: bat timed out after {timeout_sec} seconds. pid={proc.pid}, bat={bat_path}"

    if returncode != 0:
        return f"Error: bat failed. returncode={returncode}, pid={proc.pid}, bat={bat_path}"

    return f"OK: bat finished successfully. returncode=0, pid={proc.pid}, bat={bat_path}"
