from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .local_sil_runner import LocalSimulinkRunner
except ImportError:
    from local_sil_runner import LocalSimulinkRunner


_THIS_DIR = Path(__file__).resolve().parent
_AGENT_DIR = _THIS_DIR.parent
_DEFAULT_LOG_DIR = _AGENT_DIR / "log"
_SIMULATION_DIR = _DEFAULT_LOG_DIR / "simulation"
_DEFAULT_SCOPE_MAP = _SIMULATION_DIR / "scope_channel_map.json"
_DEFAULT_RAW_OUTPUT = _SIMULATION_DIR / "raw.json"
_DEFAULT_PROCESSED_OUTPUT = _SIMULATION_DIR / "processed.json"


def _default_model_path() -> Optional[str]:
    model_path = os.environ.get("GMP_LOCAL_MODEL_PATH", "").strip()
    return model_path or None


def _load_scope_map(path: str) -> Dict[str, List[str]]:
    with open(path, "r", encoding="utf-8") as fh:
        obj = json.load(fh)

    if not isinstance(obj, dict):
        raise ValueError("Scope map JSON must be an object")

    out: Dict[str, List[str]] = {}
    for k, v in obj.items():
        if not isinstance(k, str):
            continue
        if isinstance(v, list):
            out[k] = [str(x) for x in v]
        else:
            out[k] = []
    return out


def _split_result(result: Dict[str, Any]) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """Split the runner output into raw and processed JSON payloads.

    raw_payload keeps the original Scope/workspace data.
    processed_payload keeps the semantic signal view that the agent should consume.
    """
    common = {
        "status": result.get("status"),
        "diagnostics": result.get("diagnostics", {}),
        "scope_mapping_errors": result.get("scope_mapping_errors", []),
    }

    raw_payload = {
        **common,
        "raw_scopes": result.get("raw_scopes", {}),
    }

    processed_payload = {
        **common,
        "signals": result.get("signals", {}),
    }

    return raw_payload, processed_payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local Simulink model and write raw + processed JSON outputs"
    )
    parser.add_argument(
        "-m",
        "--model-path",
        default=_default_model_path(),
        help="Absolute path to local .slx model. If omitted, uses GMP_LOCAL_MODEL_PATH.",
    )
    parser.add_argument(
        "-s",
        "--scope-map",
        default=str(_DEFAULT_SCOPE_MAP),
        help="JSON file: {\"ScopeData1\": [\"speed_ref\", \"speed_fb\"], ...}",
    )
    parser.add_argument(
        "-v",
        "--scope-vars",
        nargs="*",
        default=None,
        help="Optional explicit scope variable names. Default uses keys from scope-map.",
    )
    parser.add_argument(
        "-n",
        "--session-name",
        default=None,
        help="Optional shared MATLAB session name; default connects to first found session.",
    )
    parser.add_argument(
        "--raw-output",
        default=str(_DEFAULT_RAW_OUTPUT),
        help="Output path for raw Scope/workspace data JSON",
    )
    parser.add_argument(
        "--processed-output",
        default=str(_DEFAULT_PROCESSED_OUTPUT),
        help="Output path for processed semantic signal JSON",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Backward-compatible alias for --processed-output",
    )
    parser.add_argument(
        "--no-open-ui",
        action="store_true",
        help="Do not call open_system before simulation",
    )
    return parser.parse_args()


def _write_json(path: str, payload: Dict[str, Any]) -> str:
    output_path = os.path.abspath(path)
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return output_path


def main() -> None:
    args = parse_args()

    if not args.model_path:
        raise SystemExit(
            "Missing model path. Use --model-path or set env GMP_LOCAL_MODEL_PATH first."
        )

    if args.output:
        args.processed_output = args.output

    scope_map = _load_scope_map(os.path.abspath(args.scope_map))
    runner = LocalSimulinkRunner(matlab_session_name=args.session_name)

    result = runner.run_model(
        model_path=args.model_path,
        scope_channel_map=scope_map,
        scope_vars=args.scope_vars,
        open_model_ui=not args.no_open_ui,
    )

    raw_payload, processed_payload = _split_result(result)
    raw_output_path = _write_json(args.raw_output, raw_payload)
    processed_output_path = _write_json(args.processed_output, processed_payload)

    print("=" * 70)
    print(f"status: {processed_payload['status']}")
    print(f"raw result file: {raw_output_path}")
    print(f"processed result file: {processed_output_path}")
    print("diagnostics.error_msg:", processed_payload["diagnostics"].get("error_msg"))
    print("diagnostics.matlab_lastwarn_msg:", processed_payload["diagnostics"].get("matlab_lastwarn_msg"))
    print("signals keys:", sorted(processed_payload.get("signals", {}).keys()))
    print("raw scope keys:", sorted(raw_payload.get("raw_scopes", {}).keys()))
    print("scope_mapping_errors:", processed_payload.get("scope_mapping_errors", []))
    print("=" * 70)


if __name__ == "__main__":
    main()
