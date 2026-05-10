"""
signal_loader.py

Simulation signal loading utilities for the GMP parameter iteration agent.

Responsibilities:
1. Read processed.json.
2. Validate signals under processed_json["signals"].
3. Convert each signal into a SignalSeries dataclass.
4. Resolve logical signal names from evaluation_config.signals to real
   signal names in processed.json.
5. Do not calculate any control-performance metrics here.

This module intentionally does not depend on the concrete dataclass names in
schemas.py. It accepts either:
- a plain dict with a "signals" field, or
- an object/dataclass with a .signals attribute.

Python version: 3.12+
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import math
import numbers


class SignalLoaderError(Exception):
    """Base exception for signal loading errors."""


class ProcessedJsonError(SignalLoaderError):
    """Raised when processed.json has an invalid top-level structure."""


class SignalValidationError(SignalLoaderError):
    """Raised when a signal has invalid time/value data."""


class SignalNotFoundError(SignalLoaderError):
    """Raised when a requested signal cannot be found."""


@dataclass(slots=True)
class SignalSeries:
    """
    Standard signal representation used by the evaluation layer.

    Attributes:
        name:
            Logical signal name used by evaluation_config, for example
            "actual_velocity".

            When loading raw processed.json signals directly, this is the same
            as source_name.

        source_name:
            Actual signal key in processed.json["signals"], for example
            "spd_enc.encif.speed" or "rotor_speed".

        time:
            Time vector in seconds.

        values:
            Signal value vector.

        source_scope:
            Optional original Simulink scope name, for example "ScopeData2".

        source_channel:
            Optional original channel name, for example
            "<Rotor speed wm (rad/s)>".
    """

    name: str
    source_name: str
    time: list[float]
    values: list[float]
    source_scope: str | None = None
    source_channel: str | None = None

    def __post_init__(self) -> None:
        _validate_signal_series(
            name=self.name,
            source_name=self.source_name,
            time=self.time,
            values=self.values,
        )

    @property
    def sample_count(self) -> int:
        """Number of samples in the signal."""
        return len(self.values)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable representation."""
        return {
            "name": self.name,
            "source_name": self.source_name,
            "time": self.time,
            "values": self.values,
            "source_scope": self.source_scope,
            "source_channel": self.source_channel,
            "sample_count": self.sample_count,
        }

    def with_name(self, name: str) -> "SignalSeries":
        """
        Return a copy using a different logical name.

        This is useful when mapping:
            actual_velocity -> spd_enc.encif.speed

        The source_name remains unchanged.
        """
        return SignalSeries(
            name=name,
            source_name=self.source_name,
            time=list(self.time),
            values=list(self.values),
            source_scope=self.source_scope,
            source_channel=self.source_channel,
        )


def load_processed_json(processed_json_path: str | Path) -> dict[str, Any]:
    """
    Load processed.json and validate its top-level shape.

    Args:
        processed_json_path:
            Path to processed.json.

    Returns:
        Loaded JSON object as dict.

    Raises:
        ProcessedJsonError:
            If the file does not exist, cannot be parsed, or is not a JSON
            object.
    """
    path = Path(processed_json_path)

    if not path.exists():
        raise ProcessedJsonError(f"processed.json not found: {path}")

    if not path.is_file():
        raise ProcessedJsonError(f"processed_json_path is not a file: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise ProcessedJsonError(
            f"failed to parse processed.json as JSON: {path}; "
            f"line={exc.lineno}, column={exc.colno}, msg={exc.msg}"
        ) from exc
    except OSError as exc:
        raise ProcessedJsonError(f"failed to read processed.json: {path}; {exc}") from exc

    if not isinstance(data, dict):
        raise ProcessedJsonError(
            f"processed.json root must be a JSON object, got {type(data).__name__}"
        )

    signals = data.get("signals")
    if signals is None:
        raise ProcessedJsonError('processed.json must contain top-level key "signals"')

    if not isinstance(signals, dict):
        raise ProcessedJsonError(
            f'processed.json["signals"] must be a JSON object, '
            f"got {type(signals).__name__}"
        )

    return data


def load_processed_signals(processed_json_path: str | Path) -> dict[str, SignalSeries]:
    """
    Load and validate all signals from processed.json.

    The returned dict is keyed by the real signal name in processed.json.

    Example:
        {
            "rotor_speed": SignalSeries(...),
            "actual_velocity": SignalSeries(...),
            ...
        }

    Args:
        processed_json_path:
            Path to processed.json.

    Returns:
        Dict from real processed signal name to SignalSeries.

    Raises:
        ProcessedJsonError:
            If processed.json is invalid.

        SignalValidationError:
            If any signal has invalid structure or invalid samples.
    """
    data = load_processed_json(processed_json_path)
    raw_signals = data["signals"]

    result: dict[str, SignalSeries] = {}

    for signal_name, raw_signal in raw_signals.items():
        if not isinstance(signal_name, str) or not signal_name:
            raise SignalValidationError(
                f"signal key must be a non-empty string, got {signal_name!r}"
            )

        result[signal_name] = _build_signal_series_from_raw(
            name=signal_name,
            source_name=signal_name,
            raw_signal=raw_signal,
        )

    return result


def get_config_signal_map(evaluation_config: Any) -> dict[str, str]:
    """
    Extract evaluation_config.signals as a logical-name-to-source-name map.

    Supported input forms:
    1. dict:
        {
            "signals": {
                "actual_velocity": "spd_enc.encif.speed"
            }
        }

    2. dataclass/object:
        evaluation_config.signals == {
            "actual_velocity": "spd_enc.encif.speed"
        }

    Args:
        evaluation_config:
            Dict or object containing a signals mapping.

    Returns:
        Dict mapping logical signal name to real processed.json signal name.

    Raises:
        ProcessedJsonError:
            If the signals mapping is missing or invalid.
    """
    if isinstance(evaluation_config, Mapping):
        raw_signal_map = evaluation_config.get("signals")
    else:
        raw_signal_map = getattr(evaluation_config, "signals", None)

    if raw_signal_map is None:
        raise ProcessedJsonError(
            'evaluation_config must contain a "signals" mapping or .signals attribute'
        )

    if not isinstance(raw_signal_map, Mapping):
        raise ProcessedJsonError(
            f"evaluation_config.signals must be a mapping, "
            f"got {type(raw_signal_map).__name__}"
        )

    signal_map: dict[str, str] = {}

    for logical_name, source_name in raw_signal_map.items():
        if not isinstance(logical_name, str) or not logical_name.strip():
            raise ProcessedJsonError(
                f"evaluation_config.signals contains invalid logical name: "
                f"{logical_name!r}"
            )

        if not isinstance(source_name, str) or not source_name.strip():
            raise ProcessedJsonError(
                f"evaluation_config.signals[{logical_name!r}] must be a "
                f"non-empty source signal name string, got {source_name!r}"
            )

        signal_map[logical_name.strip()] = source_name.strip()

    if not signal_map:
        raise ProcessedJsonError("evaluation_config.signals must not be empty")

    return signal_map


def resolve_signal(
    logical_name: str,
    evaluation_config: Any,
    processed_signals: Mapping[str, SignalSeries],
) -> SignalSeries:
    """
    Resolve one logical signal name to a SignalSeries.

    Example:
        evaluation_config.signals = {
            "actual_velocity": "spd_enc.encif.speed"
        }

        resolve_signal("actual_velocity", config, processed_signals)
        -> SignalSeries(name="actual_velocity",
                        source_name="spd_enc.encif.speed",
                        ...)

    Args:
        logical_name:
            Logical signal name used in evaluation_config.

        evaluation_config:
            Dict or dataclass/object containing .signals.

        processed_signals:
            Dict returned by load_processed_signals().

    Returns:
        SignalSeries with name set to logical_name and source_name set to the
        real processed.json signal name.

    Raises:
        SignalNotFoundError:
            If logical_name is not declared in evaluation_config.signals or
            the mapped source signal does not exist in processed_signals.
    """
    if not isinstance(logical_name, str) or not logical_name.strip():
        raise SignalNotFoundError(f"logical signal name must be non-empty: {logical_name!r}")

    logical_name = logical_name.strip()
    signal_map = get_config_signal_map(evaluation_config)

    if logical_name not in signal_map:
        available = ", ".join(sorted(signal_map.keys()))
        raise SignalNotFoundError(
            f"logical signal {logical_name!r} is not declared in "
            f"evaluation_config.signals. Available logical signals: [{available}]"
        )

    source_name = signal_map[logical_name]

    if source_name not in processed_signals:
        available_sources = ", ".join(sorted(processed_signals.keys()))
        raise SignalNotFoundError(
            f"logical signal {logical_name!r} maps to source signal "
            f"{source_name!r}, but that source signal does not exist in "
            f"processed.json. Available source signals: [{available_sources}]"
        )

    return processed_signals[source_name].with_name(logical_name)


def load_mapped_signals(
    processed_json_path: str | Path,
    evaluation_config: Any,
) -> dict[str, SignalSeries]:
    """
    Load processed.json and return signals keyed by logical names.

    This is the main function evaluator.py will usually call.

    Args:
        processed_json_path:
            Path to processed.json.

        evaluation_config:
            Dict or object with evaluation_config.signals mapping.

    Returns:
        Dict keyed by logical names from evaluation_config.signals.

    Example:
        {
            "actual_velocity": SignalSeries(
                name="actual_velocity",
                source_name="spd_enc.encif.speed",
                ...
            ),
            "target_velocity": SignalSeries(...)
        }
    """
    processed_signals = load_processed_signals(processed_json_path)
    signal_map = get_config_signal_map(evaluation_config)

    mapped: dict[str, SignalSeries] = {}

    for logical_name in signal_map:
        mapped[logical_name] = resolve_signal(
            logical_name=logical_name,
            evaluation_config=evaluation_config,
            processed_signals=processed_signals,
        )

    return mapped


def require_signals(
    required_logical_names: list[str] | tuple[str, ...] | set[str],
    mapped_signals: Mapping[str, SignalSeries],
) -> None:
    """
    Validate that required logical signals exist in mapped_signals.

    This helper is useful for evaluator.py before dispatching metrics.

    Args:
        required_logical_names:
            Logical names required by a metric or derived signal.

        mapped_signals:
            Dict returned by load_mapped_signals().

    Raises:
        SignalNotFoundError:
            If any required logical signal is missing.
    """
    missing = [
        name
        for name in required_logical_names
        if not isinstance(name, str) or name not in mapped_signals
    ]

    if missing:
        available = ", ".join(sorted(mapped_signals.keys()))
        raise SignalNotFoundError(
            f"missing required logical signals: {missing}. "
            f"Available logical signals: [{available}]"
        )


def _build_signal_series_from_raw(
    name: str,
    source_name: str,
    raw_signal: Any,
) -> SignalSeries:
    """
    Convert one raw signal object from processed.json into SignalSeries.
    """
    if not isinstance(raw_signal, Mapping):
        raise SignalValidationError(
            f"signal {source_name!r} must be a JSON object, "
            f"got {type(raw_signal).__name__}"
        )

    if "time" not in raw_signal:
        raise SignalValidationError(f"signal {source_name!r} is missing key 'time'")

    if "values" not in raw_signal:
        raise SignalValidationError(f"signal {source_name!r} is missing key 'values'")

    time = _coerce_numeric_list(
        value=raw_signal["time"],
        field_name="time",
        signal_name=source_name,
    )

    values = _coerce_numeric_list(
        value=raw_signal["values"],
        field_name="values",
        signal_name=source_name,
    )

    source_scope = raw_signal.get("source_scope")
    source_channel = raw_signal.get("source_channel")

    if source_scope is not None and not isinstance(source_scope, str):
        source_scope = str(source_scope)

    if source_channel is not None and not isinstance(source_channel, str):
        source_channel = str(source_channel)

    return SignalSeries(
        name=name,
        source_name=source_name,
        time=time,
        values=values,
        source_scope=source_scope,
        source_channel=source_channel,
    )


def _coerce_numeric_list(
    value: Any,
    field_name: str,
    signal_name: str,
) -> list[float]:
    """
    Convert a JSON list of numeric values into list[float].

    Rejects:
    - non-list values
    - empty lists
    - bool values
    - strings
    - None
    - NaN or +/-Inf
    - nested lists or objects
    """
    if not isinstance(value, list):
        raise SignalValidationError(
            f"signal {signal_name!r}.{field_name} must be a list, "
            f"got {type(value).__name__}"
        )

    if not value:
        raise SignalValidationError(
            f"signal {signal_name!r}.{field_name} must not be empty"
        )

    result: list[float] = []

    for index, item in enumerate(value):
        if not _is_finite_number(item):
            raise SignalValidationError(
                f"signal {signal_name!r}.{field_name}[{index}] must be a finite "
                f"number, got {item!r} ({type(item).__name__})"
            )

        result.append(float(item))

    return result


def _validate_signal_series(
    name: str,
    source_name: str,
    time: list[float],
    values: list[float],
) -> None:
    """
    Validate basic SignalSeries consistency.

    This function deliberately avoids control-performance checks. It only
    checks data integrity.
    """
    if not isinstance(name, str) or not name.strip():
        raise SignalValidationError(f"SignalSeries.name must be non-empty: {name!r}")

    if not isinstance(source_name, str) or not source_name.strip():
        raise SignalValidationError(
            f"SignalSeries.source_name must be non-empty: {source_name!r}"
        )

    if not isinstance(time, list):
        raise SignalValidationError(
            f"signal {source_name!r}.time must be list[float], "
            f"got {type(time).__name__}"
        )

    if not isinstance(values, list):
        raise SignalValidationError(
            f"signal {source_name!r}.values must be list[float], "
            f"got {type(values).__name__}"
        )

    if not time:
        raise SignalValidationError(f"signal {source_name!r}.time must not be empty")

    if not values:
        raise SignalValidationError(f"signal {source_name!r}.values must not be empty")

    if len(time) != len(values):
        raise SignalValidationError(
            f"signal {source_name!r} has mismatched time/value length: "
            f"len(time)={len(time)}, len(values)={len(values)}"
        )

    for index, item in enumerate(time):
        if not _is_finite_number(item):
            raise SignalValidationError(
                f"signal {source_name!r}.time[{index}] must be a finite number, "
                f"got {item!r}"
            )

    for index, item in enumerate(values):
        if not _is_finite_number(item):
            raise SignalValidationError(
                f"signal {source_name!r}.values[{index}] must be a finite number, "
                f"got {item!r}"
            )


def _is_finite_number(value: Any) -> bool:
    """
    Return True only for finite int/float-like numbers.

    bool is intentionally rejected because bool is a subclass of int in Python.
    """
    if isinstance(value, bool):
        return False

    if not isinstance(value, numbers.Real):
        return False

    return math.isfinite(float(value))


__all__ = [
    "SignalSeries",
    "SignalLoaderError",
    "ProcessedJsonError",
    "SignalValidationError",
    "SignalNotFoundError",
    "load_processed_json",
    "load_processed_signals",
    "get_config_signal_map",
    "resolve_signal",
    "load_mapped_signals",
    "require_signals",
]