"""
metrics.py

Deterministic metric functions for the GMP parameter-iteration agent.

Responsibilities:
1. Provide reusable mathematical/control-performance metrics.
2. Accept either SignalSeries-like objects or raw time/values lists.
3. Raise clear exceptions for invalid data or missing targets.
4. Contain no LLM, prompt, tool-call, or agent orchestration logic.

Python version: 3.12+
Dependencies: standard library only

Supported signal inputs
-----------------------
Most functions accept one of these forms:

1. SignalSeries-like object:
       final_value(signal)
       rise_time(signal, target=1000.0)

   The object must expose:
       .values
   and, for time-based metrics:
       .time

2. Raw values list:
       final_value(values=[0, 1, 2])

3. Raw time and values lists:
       rise_time(time=[0, 0.1, 0.2], values=[0, 5, 10], target=10)

4. Tuple/list pair:
       rise_time(([0, 0.1, 0.2], [0, 5, 10]), target=10)

Supported target inputs
-----------------------
For target-based metrics, target may be:

1. Scalar number:
       mean_absolute_error(signal, target=1000.0)

2. SignalSeries-like object:
       mean_absolute_error(actual_signal, target=target_signal)

3. Raw values list:
       mean_absolute_error(values=[...], target=[...])

4. Tuple/list pair:
       mean_absolute_error((time, actual_values), target=(time, target_values))

When a target vector is used, its values length must match the signal values
length. Time alignment/interpolation is intentionally not performed here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence
import math
import numbers


class MetricError(Exception):
    """Base exception for metric calculation errors."""


class SignalDataError(MetricError):
    """Raised when input signal time/value data is invalid."""


class TargetDataError(MetricError):
    """Raised when a required target is missing or invalid."""


class MetricComputationError(MetricError):
    """Raised when a metric cannot be computed from otherwise valid data."""


@dataclass(slots=True)
class MetricSignalSeries:
    """
    Lightweight signal representation returned by derived-signal functions.

    This deliberately mirrors the important fields of signal_loader.SignalSeries
    without importing signal_loader.py. Evaluator code can treat both as
    SignalSeries-like objects through duck typing.
    """

    name: str
    source_name: str
    time: list[float]
    values: list[float]
    source_scope: str | None = None
    source_channel: str | None = None

    @property
    def sample_count(self) -> int:
        return len(self.values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "source_name": self.source_name,
            "time": self.time,
            "values": self.values,
            "source_scope": self.source_scope,
            "source_channel": self.source_channel,
            "sample_count": self.sample_count,
        }


_MISSING = object()


# ---------------------------------------------------------------------------
# Public scalar metrics
# ---------------------------------------------------------------------------


def final_value(signal: Any = None, *, values: Sequence[Any] | None = None) -> float:
    """Return the last sample value."""
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    return y[-1]


def peak_value(signal: Any = None, *, values: Sequence[Any] | None = None) -> float:
    """Return the maximum sample value."""
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    return max(y)


def min_value(signal: Any = None, *, values: Sequence[Any] | None = None) -> float:
    """Return the minimum sample value."""
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    return min(y)


def peak_to_peak(signal: Any = None, *, values: Sequence[Any] | None = None) -> float:
    """Return max(values) - min(values)."""
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    return max(y) - min(y)


def mean_absolute_error(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    values: Sequence[Any] | None = None,
) -> float:
    """
    Return mean(abs(signal - target)).

    target is required and may be a scalar or a signal/vector with the same
    number of samples as signal.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    target_values = _target_to_values(target, expected_length=len(y), metric_name="mean_absolute_error")
    return sum(abs(a - b) for a, b in zip(y, target_values)) / len(y)


def rms_error(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    values: Sequence[Any] | None = None,
) -> float:
    """
    Return root-mean-square error between signal and target.

    target is required and may be a scalar or a signal/vector with the same
    number of samples as signal.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    target_values = _target_to_values(target, expected_length=len(y), metric_name="rms_error")
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(y, target_values)) / len(y))


def steady_state_error(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    values: Sequence[Any] | None = None,
    window_ratio: float = 0.1,
    window_size: int | None = None,
) -> float:
    """
    Return mean absolute error over the final steady-state window.

    The default steady-state window is the final 10% of samples, with at least
    one sample. target is required.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    target_values = _target_to_values(target, expected_length=len(y), metric_name="steady_state_error")
    start = _tail_window_start(len(y), window_ratio=window_ratio, window_size=window_size)
    tail_len = len(y) - start
    return sum(abs(y[i] - target_values[i]) for i in range(start, len(y))) / tail_len


def overshoot(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    values: Sequence[Any] | None = None,
    normalize: bool = True,
) -> float:
    """
    Return overshoot relative to the final target value.

    For an increasing response, overshoot is max(signal) - target_final.
    For a decreasing response, overshoot is target_final - min(signal).

    Negative overshoot is clamped to 0.

    If normalize=True, return overshoot ratio relative to abs(target_final).
    If abs(target_final) is near zero, absolute overshoot is returned instead
    because a meaningful ratio cannot be formed.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    target_final = _target_final_value(target, metric_name="overshoot")

    initial = y[0]
    direction = target_final - initial

    if direction >= 0:
        amount = max(y) - target_final
    else:
        amount = target_final - min(y)

    amount = max(0.0, amount)

    if not normalize:
        return amount

    denom = abs(target_final)
    if denom <= _EPSILON:
        return amount
    return amount / denom


def rise_time(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    time: Sequence[Any] | None = None,
    values: Sequence[Any] | None = None,
    lower_ratio: float = 0.1,
    upper_ratio: float = 0.9,
) -> float:
    """
    Return 10%-to-90% rise time by default.

    For a decreasing response, this function automatically uses the matching
    downward crossings. target is required and is reduced to its final value if
    a target signal/vector is provided.

    Raises MetricComputationError if the response does not reach the requested
    lower or upper threshold.
    """
    t, y = _extract_time_values(signal=signal, time=time, values=values, require_time=True)
    target_final = _target_final_value(target, metric_name="rise_time")

    _validate_ratio(lower_ratio, "lower_ratio")
    _validate_ratio(upper_ratio, "upper_ratio")
    if lower_ratio >= upper_ratio:
        raise MetricComputationError("rise_time requires lower_ratio < upper_ratio.")

    initial = y[0]
    delta = target_final - initial
    if abs(delta) <= _EPSILON:
        raise MetricComputationError(
            "rise_time cannot be computed because initial value and target are equal."
        )

    lower_level = initial + lower_ratio * delta
    upper_level = initial + upper_ratio * delta

    t_lower = _first_crossing_time(t, y, level=lower_level, direction=delta)
    if t_lower is None:
        raise MetricComputationError(
            f"rise_time lower threshold was not reached: level={lower_level}."
        )

    t_upper = _first_crossing_time(t, y, level=upper_level, direction=delta)
    if t_upper is None:
        raise MetricComputationError(
            f"rise_time upper threshold was not reached: level={upper_level}."
        )

    if t_upper < t_lower:
        raise MetricComputationError(
            "rise_time produced upper crossing before lower crossing; check signal data."
        )

    return t_upper - t_lower


def settling_time(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    time: Sequence[Any] | None = None,
    values: Sequence[Any] | None = None,
    tolerance: float | None = None,
    tolerance_ratio: float = 0.02,
) -> float:
    """
    Return the time after which the signal remains inside the target band.

    If tolerance is provided, it is treated as an absolute tolerance.
    Otherwise, tolerance_ratio * abs(target_final) is used. If target_final is
    near zero, tolerance_ratio * max(abs(signal)) is used as a fallback.

    target is required and is reduced to its final value if a target
    signal/vector is provided.
    """
    t, y = _extract_time_values(signal=signal, time=time, values=values, require_time=True)
    target_final = _target_final_value(target, metric_name="settling_time")

    band = _resolve_tolerance(
        tolerance=tolerance,
        tolerance_ratio=tolerance_ratio,
        target_final=target_final,
        values=y,
        metric_name="settling_time",
    )

    for i in range(len(y)):
        if all(abs(sample - target_final) <= band for sample in y[i:]):
            return t[i] - t[0]

    raise MetricComputationError(
        f"settling_time cannot be computed because the signal never remains within +/-{band}."
    )


def ripple(
    signal: Any = None,
    *,
    values: Sequence[Any] | None = None,
    window_ratio: float = 0.1,
    window_size: int | None = None,
) -> float:
    """
    Return peak-to-peak ripple over the final window.

    The default ripple window is the final 10% of samples, with at least one
    sample.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    start = _tail_window_start(len(y), window_ratio=window_ratio, window_size=window_size)
    tail = y[start:]
    return max(tail) - min(tail)


def zero_crossing_count(
    signal: Any = None,
    *,
    values: Sequence[Any] | None = None,
    reference: Any = 0.0,
) -> int:
    """
    Count sign crossings of signal - reference.

    reference may be a scalar or a vector/signal with the same sample count.
    Exact zero samples are ignored for sign-state purposes, so a sequence like
    [-1, 0, 1] counts as one crossing.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    reference_values = _target_to_values(
        reference,
        expected_length=len(y),
        metric_name="zero_crossing_count.reference",
    )

    count = 0
    previous_sign: int | None = None

    for sample, ref in zip(y, reference_values):
        diff = sample - ref
        if abs(diff) <= _EPSILON:
            continue
        current_sign = 1 if diff > 0 else -1
        if previous_sign is not None and current_sign != previous_sign:
            count += 1
        previous_sign = current_sign

    return count


def linear_fit_r2(
    signal: Any = None,
    *,
    time: Sequence[Any] | None = None,
    values: Sequence[Any] | None = None,
) -> float:
    """
    Return R^2 of a least-squares linear fit y = a*x + b.

    If time is unavailable, sample indices 0..N-1 are used as x values.
    A perfectly constant signal returns 1.0 because it is exactly represented
    by a horizontal line. If a time vector is present but invalid, this function
    raises SignalDataError instead of silently falling back to sample indices.
    """
    if _time_is_available(signal=signal, time=time):
        t, y = _extract_time_values(signal=signal, time=time, values=values, require_time=True)
        x = t
    else:
        _, y = _extract_time_values(signal=signal, values=values, require_time=False)
        x = [float(i) for i in range(len(y))]

    if len(y) < 2:
        raise MetricComputationError("linear_fit_r2 requires at least two samples.")

    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)

    sxx = sum((xi - x_mean) ** 2 for xi in x)
    if sxx <= _EPSILON:
        raise MetricComputationError("linear_fit_r2 cannot be computed because x has zero variance.")

    sxy = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, y))
    slope = sxy / sxx
    intercept = y_mean - slope * x_mean

    residual_sum_squares = sum((yi - (slope * xi + intercept)) ** 2 for xi, yi in zip(x, y))
    total_sum_squares = sum((yi - y_mean) ** 2 for yi in y)

    if total_sum_squares <= _EPSILON:
        return 1.0 if residual_sum_squares <= _EPSILON else 0.0

    r2 = 1.0 - residual_sum_squares / total_sum_squares
    # Floating-point noise can produce tiny excursions outside [0, 1].
    return max(0.0, min(1.0, r2))


def response_delay(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    time: Sequence[Any] | None = None,
    values: Sequence[Any] | None = None,
    threshold_ratio: float = 0.5,
) -> float:
    """
    Return the delay between target response crossing and signal crossing.

    The crossing level is computed from the signal initial value to the final
    target value:
        level = signal_initial + threshold_ratio * (target_final - signal_initial)

    If target is a time-series signal, the target crossing time is computed
    with the same level. If target is scalar, the reference crossing time is
    the signal start time. The returned value is:
        actual_crossing_time - target_crossing_time

    Positive values mean the measured signal lags the target. Negative values
    mean the signal crossed earlier than the target signal.
    """
    t, y = _extract_time_values(signal=signal, time=time, values=values, require_time=True)
    _validate_ratio(threshold_ratio, "threshold_ratio")
    target_final = _target_final_value(target, metric_name="response_delay")

    delta = target_final - y[0]
    if abs(delta) <= _EPSILON:
        raise MetricComputationError(
            "response_delay cannot be computed because signal initial value and target are equal."
        )

    level = y[0] + float(threshold_ratio) * delta
    actual_crossing = _first_crossing_time(t, y, level=level, direction=delta)
    if actual_crossing is None:
        raise MetricComputationError(
            f"response_delay actual signal did not cross threshold level={level}."
        )

    target_crossing = t[0]
    if not _is_finite_number(target):
        try:
            target_time, target_values = _extract_time_values(signal=target, require_time=True)
        except SignalDataError as exc:
            raise TargetDataError(f"response_delay target signal is invalid: {exc}") from exc
        if target_time is None:
            raise TargetDataError("response_delay target signal must provide time values.")
        target_crossing_candidate = _first_crossing_time(
            target_time,
            target_values,
            level=level,
            direction=delta,
        )
        if target_crossing_candidate is None:
            raise MetricComputationError(
                f"response_delay target signal did not cross threshold level={level}."
            )
        target_crossing = target_crossing_candidate

    return actual_crossing - target_crossing


def stability(
    signal: Any = None,
    target: Any = _MISSING,
    *,
    values: Sequence[Any] | None = None,
    window_ratio: float = 0.1,
    window_size: int | None = None,
    include_bias: bool = True,
    normalize: bool = False,
) -> float:
    """
    Return a tail-window stability cost; lower is more stable.

    The metric is deterministic and intentionally simple:
      - Without target: standard deviation of the final window.
      - With target: standard deviation of tail error; when include_bias=True,
        add abs(mean tail error) so a stable but wrong steady-state value is
        still penalized.

    If normalize=True, the cost is divided by the maximum absolute target or
    signal scale when such a scale is available. This is useful when comparing
    signals with different units.
    """
    _, y = _extract_time_values(signal=signal, values=values, require_time=False)
    start = _tail_window_start(len(y), window_ratio=window_ratio, window_size=window_size)
    tail = y[start:]

    scale_candidates = [abs(v) for v in y]

    if target is _MISSING or target is None:
        series = tail
    else:
        target_values = _target_to_values(target, expected_length=len(y), metric_name="stability")
        target_tail = target_values[start:]
        series = [sample - ref for sample, ref in zip(tail, target_tail)]
        scale_candidates.extend(abs(v) for v in target_values)

    mean_value = sum(series) / len(series)
    variance = sum((sample - mean_value) ** 2 for sample in series) / len(series)
    cost = math.sqrt(variance)
    if include_bias and target is not _MISSING and target is not None:
        cost += abs(mean_value)

    if normalize:
        scale = max(scale_candidates) if scale_candidates else 0.0
        if scale > _EPSILON:
            return cost / scale
    return cost


def numerical_derivative(
    signal: Any = None,
    *,
    time: Sequence[Any] | None = None,
    values: Sequence[Any] | None = None,
    name: str | None = None,
) -> MetricSignalSeries:
    """
    Return first-order numerical derivative dy/dt.

    The returned derivative uses interval midpoint timestamps:
        t_derivative[i] = (time[i] + time[i+1]) / 2
        value[i] = (values[i+1] - values[i]) / (time[i+1] - time[i])

    At least two samples are required. Time must be strictly increasing.
    """
    t, y = _extract_time_values(signal=signal, time=time, values=values, require_time=True)

    if len(y) < 2:
        raise MetricComputationError("numerical_derivative requires at least two samples.")

    derivative_time: list[float] = []
    derivative_values: list[float] = []

    for i in range(len(y) - 1):
        dt = t[i + 1] - t[i]
        if dt <= 0:
            raise SignalDataError(
                f"numerical_derivative requires strictly increasing time; "
                f"time[{i}]={t[i]}, time[{i + 1}]={t[i + 1]}."
            )
        derivative_time.append((t[i] + t[i + 1]) / 2.0)
        derivative_values.append((y[i + 1] - y[i]) / dt)

    source_name = _signal_attr(signal, "source_name", default="raw_signal")
    input_name = _signal_attr(signal, "name", default="signal")
    output_name = name or f"d_{input_name}_dt"

    return MetricSignalSeries(
        name=output_name,
        source_name=f"derivative({source_name})",
        time=derivative_time,
        values=derivative_values,
        source_scope=_signal_attr(signal, "source_scope", default=None),
        source_channel=_signal_attr(signal, "source_channel", default=None),
    )


# ---------------------------------------------------------------------------
# Internal data extraction and validation helpers
# ---------------------------------------------------------------------------


_EPSILON = 1e-12


def _time_is_available(*, signal: Any = None, time: Sequence[Any] | None = None) -> bool:
    if time is not None:
        return True
    if signal is None:
        return False
    if _is_time_values_pair(signal):
        return True
    return hasattr(signal, "time") and getattr(signal, "time") is not None


def _extract_time_values(
    *,
    signal: Any = None,
    time: Sequence[Any] | None = None,
    values: Sequence[Any] | None = None,
    require_time: bool,
) -> tuple[list[float] | None, list[float]]:
    """
    Normalize all supported signal input forms to (time, values).
    """
    extracted_time: Any = None
    extracted_values: Any = None

    if signal is not None and (time is not None or values is not None):
        raise SignalDataError("Provide either signal or time/values, not both.")

    if signal is not None:
        extracted_time, extracted_values = _extract_from_signal_like(signal)
    else:
        extracted_time = time
        extracted_values = values

    if extracted_values is None:
        raise SignalDataError("Signal values are required but were not provided.")

    y = _coerce_numeric_list(extracted_values, field_name="values")

    if require_time:
        if extracted_time is None:
            raise SignalDataError("Signal time is required for this metric but was not provided.")
        t = _coerce_numeric_list(extracted_time, field_name="time")
        _validate_time_and_values(t, y)
        return t, y

    if extracted_time is not None:
        t = _coerce_numeric_list(extracted_time, field_name="time")
        _validate_time_and_values(t, y)
        return t, y

    return None, y


def _extract_from_signal_like(signal: Any) -> tuple[Any, Any]:
    """
    Extract (time, values) from a supported signal-like object.
    """
    if _is_time_values_pair(signal):
        return signal[0], signal[1]

    if hasattr(signal, "values"):
        return getattr(signal, "time", None), getattr(signal, "values")

    # A plain list such as [1, 2, 3] is interpreted as values-only input.
    if _is_sequence_but_not_text(signal):
        return None, signal

    raise SignalDataError(
        "Unsupported signal input. Expected a SignalSeries-like object, "
        "a values list, or a (time, values) pair."
    )


def _is_time_values_pair(value: Any) -> bool:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return False
    first, second = value[0], value[1]
    return _is_sequence_but_not_text(first) and _is_sequence_but_not_text(second)


def _is_sequence_but_not_text(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


def _coerce_numeric_list(value: Any, *, field_name: str) -> list[float]:
    if not _is_sequence_but_not_text(value):
        raise SignalDataError(f"{field_name} must be a non-empty numeric sequence.")

    if len(value) == 0:
        raise SignalDataError(f"{field_name} must not be empty.")

    result: list[float] = []
    for index, item in enumerate(value):
        if not _is_finite_number(item):
            raise SignalDataError(
                f"{field_name}[{index}] must be a finite number, got {item!r} "
                f"({type(item).__name__})."
            )
        result.append(float(item))

    return result


def _validate_time_and_values(time: list[float], values: list[float]) -> None:
    if len(time) != len(values):
        raise SignalDataError(
            f"time and values length mismatch: len(time)={len(time)}, len(values)={len(values)}."
        )
    for i in range(1, len(time)):
        if time[i] <= time[i - 1]:
            raise SignalDataError(
                f"time must be strictly increasing: time[{i - 1}]={time[i - 1]}, "
                f"time[{i}]={time[i]}."
            )


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, numbers.Real):
        return False
    return math.isfinite(float(value))


def _target_to_values(target: Any, *, expected_length: int, metric_name: str) -> list[float]:
    if target is _MISSING or target is None:
        raise TargetDataError(f"{metric_name} requires target, but target was not provided.")

    if _is_finite_number(target):
        return [float(target)] * expected_length

    try:
        _, target_values = _extract_time_values(signal=target, require_time=False)
    except SignalDataError as exc:
        raise TargetDataError(f"{metric_name} target is invalid: {exc}") from exc

    if len(target_values) != expected_length:
        raise TargetDataError(
            f"{metric_name} target length mismatch: expected {expected_length}, "
            f"got {len(target_values)}."
        )

    return target_values


def _target_final_value(target: Any, *, metric_name: str) -> float:
    if target is _MISSING or target is None:
        raise TargetDataError(f"{metric_name} requires target, but target was not provided.")

    if _is_finite_number(target):
        return float(target)

    try:
        _, target_values = _extract_time_values(signal=target, require_time=False)
    except SignalDataError as exc:
        raise TargetDataError(f"{metric_name} target is invalid: {exc}") from exc
    return target_values[-1]


def _tail_window_start(
    length: int,
    *,
    window_ratio: float,
    window_size: int | None,
) -> int:
    if length <= 0:
        raise SignalDataError("Cannot create tail window for empty signal.")

    if window_size is not None:
        if isinstance(window_size, bool) or not isinstance(window_size, int):
            raise SignalDataError("window_size must be an integer when provided.")
        if window_size <= 0:
            raise SignalDataError("window_size must be positive when provided.")
        size = min(length, window_size)
    else:
        _validate_ratio(window_ratio, "window_ratio")
        size = max(1, int(math.ceil(length * window_ratio)))

    return length - size


def _validate_ratio(value: Any, field_name: str) -> None:
    if not _is_finite_number(value):
        raise SignalDataError(f"{field_name} must be a finite number.")
    if float(value) < 0 or float(value) > 1:
        raise SignalDataError(f"{field_name} must be in [0, 1].")


def _resolve_tolerance(
    *,
    tolerance: float | None,
    tolerance_ratio: float,
    target_final: float,
    values: list[float],
    metric_name: str,
) -> float:
    if tolerance is not None:
        if not _is_finite_number(tolerance):
            raise SignalDataError(f"{metric_name} tolerance must be a finite number.")
        band = float(tolerance)
        if band < 0:
            raise SignalDataError(f"{metric_name} tolerance must be >= 0.")
        return band

    _validate_ratio(tolerance_ratio, "tolerance_ratio")

    scale = abs(target_final)
    if scale <= _EPSILON:
        scale = max(abs(v) for v in values)
    if scale <= _EPSILON:
        # All-zero signal and zero target: exact equality is a reasonable band.
        return 0.0
    return float(tolerance_ratio) * scale


def _first_crossing_time(
    time: list[float],
    values: list[float],
    *,
    level: float,
    direction: float,
) -> float | None:
    """
    Return first linearly interpolated threshold crossing time.
    """
    increasing = direction >= 0

    for i, sample in enumerate(values):
        reached = sample >= level if increasing else sample <= level
        if not reached:
            continue

        if i == 0:
            return time[0]

        previous = values[i - 1]
        previous_time = time[i - 1]
        current_time = time[i]

        denom = sample - previous
        if abs(denom) <= _EPSILON:
            return current_time

        ratio = (level - previous) / denom
        ratio = max(0.0, min(1.0, ratio))
        return previous_time + ratio * (current_time - previous_time)

    return None


def _signal_attr(signal: Any, attr_name: str, *, default: Any) -> Any:
    if signal is None:
        return default
    return getattr(signal, attr_name, default)


__all__ = [
    "MetricError",
    "SignalDataError",
    "TargetDataError",
    "MetricComputationError",
    "MetricSignalSeries",
    "final_value",
    "peak_value",
    "min_value",
    "peak_to_peak",
    "mean_absolute_error",
    "rms_error",
    "steady_state_error",
    "overshoot",
    "rise_time",
    "settling_time",
    "ripple",
    "zero_crossing_count",
    "linear_fit_r2",
    "response_delay",
    "stability",
    "numerical_derivative",
]
