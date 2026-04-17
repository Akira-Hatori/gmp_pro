from __future__ import annotations

import argparse
import json
import os
from typing import Dict, List

try:
    from .local_sil_runner import LocalSimulinkRunner
except ImportError:
    from local_sil_runner import LocalSimulinkRunner


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run local Simulink model and collect diagnostics + mapped scope signals"
    )
    parser.add_argument("--model-path", required=True, help="Absolute path to local .slx model")
    parser.add_argument(
        "--scope-map",
        required=True,
        help="JSON file: {\"ScopeData1\": [\"speed_ref\", \"speed_fb\"], ...}",
    )
    parser.add_argument(
        "--scope-vars",
        nargs="*",
        default=None,
        help="Optional explicit scope variable names. Default uses keys from scope-map.",
    )
    parser.add_argument(
        "--session-name",
        default=None,
        help="Optional shared MATLAB session name; default connects to first found session.",
    )
    parser.add_argument(
        "--output",
        default="run_result.json",
        help="Output JSON path",
    )
    parser.add_argument(
        "--no-open-ui",
        action="store_true",
        help="Do not call open_system before simulation",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    scope_map = _load_scope_map(args.scope_map)
    runner = LocalSimulinkRunner(matlab_session_name=args.session_name)

    result = runner.run_model(
        model_path=args.model_path,
        scope_channel_map=scope_map,
        scope_vars=args.scope_vars,
        open_model_ui=not args.no_open_ui,
    )

    output_path = os.path.abspath(args.output)
    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    print("=" * 70)
    print(f"status: {result['status']}")
    print(f"result file: {output_path}")
    print("diagnostics.error_msg:", result["diagnostics"].get("error_msg"))
    print("diagnostics.matlab_lastwarn_msg:", result["diagnostics"].get("matlab_lastwarn_msg"))
    print("signals keys:", sorted(result.get("signals", {}).keys()))
    print("scope_mapping_errors:", result.get("scope_mapping_errors", []))
    print("=" * 70)


if __name__ == "__main__":
    main()
