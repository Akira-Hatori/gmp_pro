"""
Evaluation package for the GMP parameter-iteration agent.

This package contains deterministic evaluation utilities:
- schemas.py: evaluation configuration dataclasses and validation helpers
- signal_loader.py: processed.json loading and logical-signal mapping
- metrics.py: deterministic mathematical/control-performance metrics
- evaluator.py: config + signals + metrics execution
- scoring.py: metric normalization and overall_score calculation
- result_writer.py: JSON and text-summary output helpers

The package intentionally contains no LLM logic and no engineering-file
modification logic.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__version__ = "0.1.1"

_EXPORT_MODULES: dict[str, str] = {
    # schemas
    "EvaluationConfig": "schemas",
    "EvaluationConfigError": "schemas",
    "MetricConfig": "schemas",
    "SUPPORTED_METRIC_NAMES": "schemas",
    "SUPPORTED_OPTIMIZATION_DIRECTIONS": "schemas",
    "load_evaluation_config_from_dict": "schemas",
    "load_evaluation_config_from_json": "schemas",
    "validate_evaluation_config": "schemas",
    # signal_loader
    "SignalSeries": "signal_loader",
    "SignalLoaderError": "signal_loader",
    "ProcessedJsonError": "signal_loader",
    "SignalValidationError": "signal_loader",
    "SignalNotFoundError": "signal_loader",
    "load_processed_json": "signal_loader",
    "load_processed_signals": "signal_loader",
    "load_mapped_signals": "signal_loader",
    "resolve_signal": "signal_loader",
    "require_signals": "signal_loader",
    # metrics
    "MetricError": "metrics",
    "SignalDataError": "metrics",
    "TargetDataError": "metrics",
    "MetricComputationError": "metrics",
    "MetricSignalSeries": "metrics",
    "final_value": "metrics",
    "peak_value": "metrics",
    "min_value": "metrics",
    "peak_to_peak": "metrics",
    "mean_absolute_error": "metrics",
    "rms_error": "metrics",
    "steady_state_error": "metrics",
    "overshoot": "metrics",
    "rise_time": "metrics",
    "settling_time": "metrics",
    "ripple": "metrics",
    "zero_crossing_count": "metrics",
    "linear_fit_r2": "metrics",
    "response_delay": "metrics",
    "stability": "metrics",
    "numerical_derivative": "metrics",
    # evaluator
    "EvaluatorError": "evaluator",
    "DerivedSignalError": "evaluator",
    "evaluate_simulation": "evaluator",
    "evaluate_simulation_from_config": "evaluator",
    "write_evaluation_result": "evaluator",
    # scoring
    "ScoringError": "scoring",
    "ThresholdConfigError": "scoring",
    "MetricScoreError": "scoring",
    "score_metric": "scoring",
    "calculate_overall_score": "scoring",
    "score_metric_results": "scoring",
    "add_scores_to_evaluation_result": "scoring",
    # result_writer
    "ResultWriterError": "result_writer",
    "JsonResultWriteError": "result_writer",
    "TextSummaryWriteError": "result_writer",
    "write_json_result": "result_writer",
    "write_text_summary": "result_writer",
    "write_evaluation_outputs": "result_writer",
    "build_text_summary": "result_writer",
}


def __getattr__(name: str) -> Any:
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(f".{module_name}", __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORT_MODULES))


__all__ = ["__version__", *_EXPORT_MODULES.keys()]
