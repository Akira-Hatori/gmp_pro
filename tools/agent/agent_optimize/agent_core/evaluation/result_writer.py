"""
result_writer.py

Result writing utilities for the GMP parameter-iteration agent evaluation layer.

Responsibilities:
1. Write evaluation result dictionaries to JSON files with readable indentation.
2. Write human-readable text summaries for quick inspection.
3. Handle Windows paths, relative paths, and non-ASCII paths through pathlib.
4. Avoid any LLM, prompt, tool-call, or agent orchestration logic.

Python version: 3.12+
Dependencies: standard library only

Suggested output files:
    tools/agent/log/evaluation_config.json
    tools/agent/log/evaluation_result.json
    tools/agent/log/evaluation_summary.txt

Later, the same functions can be used for per-iteration directories:
    tools/agent/log/iteration_001/evaluation_result.json
    tools/agent/log/iteration_001/evaluation_summary.txt
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
import json


class ResultWriterError(Exception):
    """Base exception for result writing errors."""


class JsonResultWriteError(ResultWriterError):
    """Raised when writing JSON output fails."""


class TextSummaryWriteError(ResultWriterError):
    """Raised when writing text summary output fails."""


def write_json_result(result: dict[str, Any], path: str | Path) -> Path:
    """
    Write an evaluation result dict to a UTF-8 JSON file.

    Args:
        result: Evaluation result dictionary, usually returned by evaluator.py
            or scoring.py.
        path: Output path. Parent directories are created automatically.

    Returns:
        The Path object used for writing.

    Raises:
        JsonResultWriteError: If result is not a dict, cannot be serialized, or
            cannot be written.
    """
    if not isinstance(result, dict):
        raise JsonResultWriteError(
            f"write_json_result expects result to be dict, got {type(result).__name__}."
        )

    output_path = Path(path)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(
                _json_safe(result),
                f,
                ensure_ascii=False,
                indent=2,
                sort_keys=False,
            )
            f.write("\n")
    except (TypeError, ValueError, OSError) as exc:
        raise JsonResultWriteError(
            f"failed to write JSON result to {output_path}: {exc}"
        ) from exc

    return output_path


def write_text_summary(result: dict[str, Any], path: str | Path) -> Path:
    """
    Write a human-readable evaluation summary to a UTF-8 text file.

    Args:
        result: Evaluation result dictionary, usually returned by evaluator.py
            or scoring.py.
        path: Output path. Parent directories are created automatically.

    Returns:
        The Path object used for writing.

    Raises:
        TextSummaryWriteError: If result is not a dict or the file cannot be
            written.
    """
    if not isinstance(result, dict):
        raise TextSummaryWriteError(
            f"write_text_summary expects result to be dict, got {type(result).__name__}."
        )

    output_path = Path(path)
    text = build_text_summary(result)
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8", newline="\n") as f:
            f.write(text)
            if not text.endswith("\n"):
                f.write("\n")
    except OSError as exc:
        raise TextSummaryWriteError(
            f"failed to write text summary to {output_path}: {exc}"
        ) from exc

    return output_path


def write_evaluation_outputs(
    result: dict[str, Any],
    output_dir: str | Path,
    *,
    result_filename: str = "evaluation_result.json",
    summary_filename: str = "evaluation_summary.txt",
) -> dict[str, str]:
    """
    Convenience helper that writes both JSON result and text summary.

    Returns:
        {
          "json_path": "...",
          "summary_path": "..."
        }
    """
    base_dir = Path(output_dir)
    json_path = write_json_result(result, base_dir / result_filename)
    summary_path = write_text_summary(result, base_dir / summary_filename)
    return {
        "json_path": str(json_path),
        "summary_path": str(summary_path),
    }


def build_text_summary(result: Mapping[str, Any]) -> str:
    """
    Build a human-readable summary string from an evaluation result.

    Exposed separately so tests and future tools can preview the summary
    without writing a file.
    """
    if not isinstance(result, Mapping):
        raise TextSummaryWriteError(
            f"build_text_summary expects result to be mapping/dict, got {type(result).__name__}."
        )

    lines: list[str] = []
    lines.append("GMP Evaluation Summary")
    lines.append("=" * 80)
    lines.append(f"Generated At      : {_timestamp()}")
    lines.append(f"Status            : {_fmt(result.get('status'))}")
    lines.append(f"Task Type         : {_fmt(result.get('task_type'))}")
    lines.append(f"Objective         : {_fmt(result.get('objective'))}")

    if "overall_score" in result:
        lines.append(f"Overall Score     : {_fmt_number(result.get('overall_score'))}")

    scoring_summary = result.get("scoring_summary")
    if isinstance(scoring_summary, Mapping):
        lines.append("-" * 80)
        lines.append("Scoring Summary")
        lines.append(f"  Scored Metrics  : {_fmt(scoring_summary.get('scored_metric_count'))}")
        lines.append(f"  Skipped Metrics : {_fmt(scoring_summary.get('skipped_metric_count'))}")
        lines.append(f"  Total Weight    : {_fmt_number(scoring_summary.get('total_score_weight'))}")

    lines.append("-" * 80)
    lines.append("Metric Counts")
    lines.append(f"  Configured      : {_fmt(result.get('configured_metric_count'))}")
    lines.append(f"  OK              : {_fmt(result.get('metric_ok_count'))}")
    lines.append(f"  Error           : {_fmt(result.get('metric_error_count'))}")

    metrics = result.get("metrics")
    if isinstance(metrics, Mapping) and metrics:
        lines.append("-" * 80)
        lines.append("Metrics")
        lines.append(
            "  {name:<32} {status:<8} {value:<16} {score:<10} {weight:<10} {direction}".format(
                name="Name",
                status="Status",
                value="Value",
                score="Score",
                weight="Weight",
                direction="Direction",
            )
        )
        lines.append("  " + "-" * 110)
        for metric_name, metric_result in metrics.items():
            if isinstance(metric_result, Mapping):
                lines.append(_format_metric_line(str(metric_name), metric_result))
                error = metric_result.get("error") or metric_result.get("score_error")
                if error:
                    lines.append(f"    error: {error}")
            else:
                lines.append(f"  {str(metric_name):<32} <invalid metric result>")

    derived_signals = result.get("derived_signals")
    if isinstance(derived_signals, Mapping) and derived_signals:
        lines.append("-" * 80)
        lines.append("Derived Signals")
        for name, summary in derived_signals.items():
            if isinstance(summary, Mapping):
                lines.append(
                    f"  {name}: samples={_fmt(summary.get('sample_count'))}, "
                    f"source={_fmt(summary.get('source_name'))}, "
                    f"first={_fmt_number(summary.get('value_first'))}, "
                    f"last={_fmt_number(summary.get('value_last'))}"
                )
            else:
                lines.append(f"  {name}: {_fmt(summary)}")

    warnings = result.get("warnings")
    if isinstance(warnings, list) and warnings:
        lines.append("-" * 80)
        lines.append("Warnings")
        for index, warning in enumerate(warnings, start=1):
            lines.append(f"  {index}. {_fmt(warning)}")

    errors = result.get("errors")
    if isinstance(errors, list) and errors:
        lines.append("-" * 80)
        lines.append("Errors")
        for index, error in enumerate(errors, start=1):
            lines.append(f"  {index}. {_format_error(error)}")

    lines.append("=" * 80)
    return "\n".join(lines) + "\n"


def _format_metric_line(metric_name: str, metric_result: Mapping[str, Any]) -> str:
    return (
        "  {name:<32} {status:<8} {value:<16} {score:<10} {weight:<10} {direction}".format(
            name=_clip(metric_name, 32),
            status=_clip(_fmt(metric_result.get("status")), 8),
            value=_clip(_fmt_number(metric_result.get("value")), 16),
            score=_clip(_fmt_number(metric_result.get("score")), 10),
            weight=_clip(_fmt_number(metric_result.get("weight")), 10),
            direction=_fmt(metric_result.get("optimization_direction")),
        )
    )


def _format_error(error: Any) -> str:
    if isinstance(error, Mapping):
        stage = error.get("stage")
        err_type = error.get("type")
        message = error.get("message")
        pieces = []
        if stage is not None:
            pieces.append(f"stage={stage}")
        if err_type is not None:
            pieces.append(f"type={err_type}")
        if message is not None:
            pieces.append(f"message={message}")
        if pieces:
            return "; ".join(pieces)
    return _fmt(error)


def _json_safe(value: Any) -> Any:
    """Convert common Python objects to JSON-serializable values."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _json_safe(value.to_dict())
    if is_dataclass(value):
        return _json_safe(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return repr(value)


def _timestamp() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    return str(value)


def _fmt_number(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{float(value):.6g}"
    return str(value)


def _clip(text: str, width: int) -> str:
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


__all__ = [
    "ResultWriterError",
    "JsonResultWriteError",
    "TextSummaryWriteError",
    "write_json_result",
    "write_text_summary",
    "write_evaluation_outputs",
    "build_text_summary",
]
