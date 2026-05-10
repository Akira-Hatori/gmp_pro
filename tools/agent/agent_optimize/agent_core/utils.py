from pathlib import Path
from .constants import DEFAULT_MAX_CHARS


def read_text_file(path: Path) -> str:
    encodings = ["utf-8-sig", "utf-8", "gbk", "gb2312", "latin-1"]
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="replace")


def truncate_text(text: str, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    if max_chars <= 0:
        max_chars = DEFAULT_MAX_CHARS
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + f"\n\n[TRUNCATED: returned first {max_chars} characters only.]"


def read_text_if_exists(path: Path, max_chars: int = DEFAULT_MAX_CHARS) -> str:
    if not path.exists() or not path.is_file():
        return f"[missing file: {path}]"
    try:
        return truncate_text(read_text_file(path), max_chars)
    except OSError as exc:
        return f"[failed to read file: {path}] {exc}"


def is_inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def file_updated_after(path: Path, since: float, slack_sec: float = 1.0) -> bool:
    try:
        return path.exists() and path.stat().st_mtime >= since - slack_sec
    except OSError:
        return False
