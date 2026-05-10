"""
scoring.py

Overall scoring utilities for the GMP parameter-iteration agent.

Responsibilities:
1. Convert individual metric values to normalized 0..100 scores.
2. Aggregate scored metrics into an overall_score using metric weights.
3. Skip metrics that do not define good_threshold and bad_threshold.
4. Preserve raw metric results; scoring functions return enriched copies and
   do not mutate inputs unless the caller explicitly chooses to use the copy.
5. Contain no LLM, prompt, tool-call, or agent orchestration logic.

Python version: 3.12+
Dependencies: standard library only

Expected metric result shape
----------------------------
This module is designed to work with evaluator.py output:

{
  "metrics": {
    "steady_state_error": {
      "status": "ok",
      "value": 0.015,
      "weight": 0.25,
      "optimization_direction": "minimize",
      "extra": {
        "good_threshold": 0.01,
        "bad_threshold": 0.2
      }
    }
  }
}

Thresholds may be placed either at metric-result top level or inside
metric_result["extra"]. This is intentional because schemas.py preserves
unknown metric config fields such as good_threshold and bad_threshold in
MetricConfig.extra.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping
import math
import numbers


class ScoringError(Exception):
    """Base exception for scoring errors."""


class ThresholdConfigError(ScoringError):
    """Raised when good_threshold/bad_threshold are invalid."""


class MetricScoreError(ScoringError):
    """Raised when one metric cannot be scored."""


_SCORE_MIN = 0.0
_SCORE_MAX = 100.0
_EPSILON = 1e-12


_SCOREABLE_DIRECTIONS = {"minimize", "maximize"}


_SKIP_REASON_NOT_OK = "metric status is not ok"
_SKIP_REASON_NO_VALUE = "metric value is missing or non-scalar"
_SKIP_REASON_NO_THRESHOLD = "good_threshold or bad_threshold is missing"
_SKIP_REASON_ZERO_WEIGHT = "metric weight is zero"
_SKIP_REASON_UNSCORED_DIRECTION = "optimization_direction is not minimize/maximize"


def score_metric(
    value: float,
    good_threshold: float,
    bad_threshold: float,
    optimization_direction: str,
) -> float:
    """
    Normalize one metric value to a 0..100 score.

    For optimization_direction="minimize":
        - value <= good_threshold -> 100
        - value >= bad_threshold  -> 0
        - linear interpolation in between

    For optimization_direction="maximize":
        - value >= good_threshold -> 100
        - value <= bad_threshold  -> 0
        - linear interpolation in between

    Args:
        value:
            Scalar metric value.

        good_threshold:
            Value considered good enough.

        bad_threshold:
            Value considered unacceptable.

        optimization_direction:
            "minimize" or "maximize".

    Returns:
        Score in [0, 100].

    Raises:
        ThresholdConfigError:
            If thresholds are missing, non-finite, equal, or have the wrong
            ordering for the direction.

        MetricScoreError:
            If value is not a finite scalar or direction is unsupported.
    """
    metric_value = _coerce_finite_float(value, "value", MetricScoreError)
    good = _coerce_finite_float(good_threshold, "good_threshold", ThresholdConfigError)
    bad = _coerce_finite_float(bad_threshold, "bad_threshold", ThresholdConfigError)
    direction = _normalize_direction(optimization_direction)

    if direction == "minimize":
        if good >= bad:
            raise ThresholdConfigError(
                "For minimize metrics, good_threshold must be smaller than bad_threshold. "
                f"Got good_threshold={good}, bad_threshold={bad}."
            )
        if metric_value <= good:
            return _SCORE_MAX
        if metric_value >= bad:
            return _SCORE_MIN
        return _clamp_score((bad - metric_value) / (bad - good) * _SCORE_MAX)

    if direction == "maximize":
        if good <= bad:
            raise ThresholdConfigError(
                "For maximize metrics, good_threshold must be larger than bad_threshold. "
                f"Got good_threshold={good}, bad_threshold={bad}."
            )
        if metric_value >= good:
            return _SCORE_MAX
        if metric_value <= bad:
            return _SCORE_MIN
        return _clamp_score((metric_value - bad) / (good - bad) * _SCORE_MAX)

    raise MetricScoreError(
        f"optimization_direction must be 'minimize' or 'maximize', got {optimization_direction!r}."
    )


def calculate_overall_score(metric_results: Mapping[str, Any]) -> float | None:
    """
    Calculate weighted overall_score from metric result mapping.

    Only metrics satisfying all of the following participate:
        1. metric_result["status"] == "ok"
        2. metric_result["value"] is a finite scalar
        3. good_threshold and bad_threshold are present
        4. optimization_direction is "minimize" or "maximize"
        5. weight > 0

    Metrics without thresholds are skipped, not treated as errors. This lets
    evaluator.py still report raw metric values before a scoring policy exists.

    Args:
        metric_results:
            Usually evaluation_result["metrics"]. It may also be a plain dict
            of metric_name -> metric_result.

    Returns:
        Weighted score in [0, 100], or None if no metric can participate.

    Raises:
        ScoringError:
            If metric_results is malformed or a metric declares thresholds with
            invalid ordering/types.
    """
    scored = score_metric_results(metric_results)
    return scored["overall_score"]


def score_metric_results(metric_results: Mapping[str, Any]) -> dict[str, Any]:
    """
    Return a scored copy of a metric result mapping.

    This is the detailed companion to calculate_overall_score(). It preserves
    every raw metric result and annotates each metric with:
        - score
        - score_status
        - score_skip_reason
        - score_error

    The return object has this shape:

    {
      "overall_score": 86.5,
      "scored_metric_count": 3,
      "skipped_metric_count": 2,
      "total_score_weight": 0.75,
      "metrics": {... enriched metric results ...},
      "warnings": [...]
    }
    """
    if not isinstance(metric_results, Mapping):
        raise ScoringError(
            f"metric_results must be a mapping/dict, got {type(metric_results).__name__}."
        )

    enriched_metrics: dict[str, Any] = {}
    warnings: list[str] = []
    weighted_sum = 0.0
    total_weight = 0.0
    scored_count = 0
    skipped_count = 0

    for metric_key, raw_metric_result in metric_results.items():
        if not isinstance(metric_key, str) or not metric_key.strip():
            raise ScoringError(f"metric result key must be a non-empty string, got {metric_key!r}.")
        if not isinstance(raw_metric_result, Mapping):
            raise ScoringError(
                f"metric_results[{metric_key!r}] must be a mapping/dict, "
                f"got {type(raw_metric_result).__name__}."
            )

        metric_copy = deepcopy(dict(raw_metric_result))
        score_info = _try_score_one_metric(metric_key, metric_copy)
        metric_copy.update(score_info)
        enriched_metrics[metric_key] = metric_copy

        if score_info["score_status"] == "scored":
            score_value = score_info["score"]
            weight = score_info["score_weight"]
            weighted_sum += score_value * weight
            total_weight += weight
            scored_count += 1
        else:
            skipped_count += 1
            reason = score_info.get("score_skip_reason") or score_info.get("score_error")
            warnings.append(f"metric {metric_key!r} skipped from overall_score: {reason}")

    overall_score = None if total_weight <= _EPSILON else _clamp_score(weighted_sum / total_weight)

    return {
        "overall_score": overall_score,
        "scored_metric_count": scored_count,
        "skipped_metric_count": skipped_count,
        "total_score_weight": total_weight,
        "metrics": enriched_metrics,
        "warnings": warnings,
    }


def add_scores_to_evaluation_result(evaluation_result: Mapping[str, Any]) -> dict[str, Any]:
    """
    Return an enriched copy of evaluator.py result with scoring fields added.

    Args:
        evaluation_result:
            Dict returned by evaluator.evaluate_simulation().

    Returns:
        A new dict with:
            - overall_score
            - scoring_summary
            - metrics[*].score fields

    Notes:
        The input object is not mutated.
    """
    if not isinstance(evaluation_result, Mapping):
        raise ScoringError(
            f"evaluation_result must be a mapping/dict, got {type(evaluation_result).__name__}."
        )

    metrics_obj = evaluation_result.get("metrics")
    if not isinstance(metrics_obj, Mapping):
        raise ScoringError('evaluation_result must contain a mapping field "metrics".')

    scored = score_metric_results(metrics_obj)
    result_copy = deepcopy(dict(evaluation_result))
    result_copy["metrics"] = scored["metrics"]
    result_copy["overall_score"] = scored["overall_score"]
    result_copy["scoring_summary"] = {
        "overall_score": scored["overall_score"],
        "scored_metric_count": scored["scored_metric_count"],
        "skipped_metric_count": scored["skipped_metric_count"],
        "total_score_weight": scored["total_score_weight"],
    }

    existing_warnings = result_copy.get("warnings")
    if isinstance(existing_warnings, list):
        result_copy["warnings"] = existing_warnings + scored["warnings"]
    else:
        result_copy["warnings"] = scored["warnings"]

    return result_copy


def _try_score_one_metric(metric_key: str, metric_result: Mapping[str, Any]) -> dict[str, Any]:
    status = metric_result.get("status")
    if status != "ok":
        return _skipped(_SKIP_REASON_NOT_OK)

    value = metric_result.get("value")
    if not _is_finite_number(value):
        return _skipped(_SKIP_REASON_NO_VALUE)

    direction = metric_result.get("optimization_direction", "none")
    if direction not in _SCOREABLE_DIRECTIONS:
        return _skipped(_SKIP_REASON_UNSCORED_DIRECTION)

    weight = metric_result.get("weight", 1.0)
    try:
        score_weight = _coerce_finite_float(weight, f"{metric_key}.weight", MetricScoreError)
    except MetricScoreError as exc:
        return _score_error(exc)
    if score_weight < 0:
        return _score_error(MetricScoreError(f"{metric_key}.weight must be >= 0."))
    if score_weight <= _EPSILON:
        return _skipped(_SKIP_REASON_ZERO_WEIGHT, score_weight=score_weight)

    thresholds = _extract_thresholds(metric_result)
    if thresholds is None:
        return _skipped(_SKIP_REASON_NO_THRESHOLD, score_weight=score_weight)

    good_threshold, bad_threshold = thresholds

    try:
        score = score_metric(
            value=float(value),
            good_threshold=good_threshold,
            bad_threshold=bad_threshold,
            optimization_direction=str(direction),
        )
    except ScoringError as exc:
        return _score_error(exc, score_weight=score_weight)

    return {
        "score_status": "scored",
        "score": score,
        "score_weight": score_weight,
        "score_good_threshold": float(good_threshold),
        "score_bad_threshold": float(bad_threshold),
        "score_optimization_direction": direction,
        "score_skip_reason": None,
        "score_error": None,
    }


def _extract_thresholds(metric_result: Mapping[str, Any]) -> tuple[float, float] | None:
    good_raw = metric_result.get("good_threshold")
    bad_raw = metric_result.get("bad_threshold")

    extra = metric_result.get("extra")
    if isinstance(extra, Mapping):
        if good_raw is None:
            good_raw = extra.get("good_threshold")
        if bad_raw is None:
            bad_raw = extra.get("bad_threshold")

    if good_raw is None or bad_raw is None:
        return None

    good = _coerce_finite_float(good_raw, "good_threshold", ThresholdConfigError)
    bad = _coerce_finite_float(bad_raw, "bad_threshold", ThresholdConfigError)
    return good, bad


def _skipped(reason: str, *, score_weight: float | None = None) -> dict[str, Any]:
    return {
        "score_status": "skipped",
        "score": None,
        "score_weight": score_weight,
        "score_good_threshold": None,
        "score_bad_threshold": None,
        "score_optimization_direction": None,
        "score_skip_reason": reason,
        "score_error": None,
    }


def _score_error(exc: Exception, *, score_weight: float | None = None) -> dict[str, Any]:
    return {
        "score_status": "error",
        "score": None,
        "score_weight": score_weight,
        "score_good_threshold": None,
        "score_bad_threshold": None,
        "score_optimization_direction": None,
        "score_skip_reason": None,
        "score_error": f"{type(exc).__name__}: {exc}",
    }


def _normalize_direction(optimization_direction: Any) -> str:
    if not isinstance(optimization_direction, str):
        raise MetricScoreError(
            f"optimization_direction must be a string, got {type(optimization_direction).__name__}."
        )
    direction = optimization_direction.strip().lower()
    if direction not in _SCOREABLE_DIRECTIONS:
        raise MetricScoreError(
            f"optimization_direction must be 'minimize' or 'maximize', got {optimization_direction!r}."
        )
    return direction


def _coerce_finite_float(value: Any, field_name: str, exc_type: type[Exception]) -> float:
    if not _is_finite_number(value):
        raise exc_type(f"{field_name} must be a finite number, got {value!r}.")
    return float(value)


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, numbers.Real):
        return False
    return math.isfinite(float(value))


def _clamp_score(value: float) -> float:
    if value < _SCORE_MIN:
        return _SCORE_MIN
    if value > _SCORE_MAX:
        return _SCORE_MAX
    # Keep output stable and JSON-friendly without over-rounding useful detail.
    return round(float(value), 6)


__all__ = [
    "ScoringError",
    "ThresholdConfigError",
    "MetricScoreError",
    "score_metric",
    "calculate_overall_score",
    "score_metric_results",
    "add_scores_to_evaluation_result",
]
