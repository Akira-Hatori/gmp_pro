# agent_silhelper (local-only v1)

This folder is a clean local-only helper for your first phase:

- Agent, control kernel, and Simulink all run on the same PC.
- Python only does three things:
  1) connect shared MATLAB session,
  2) open and run local .slx model,
  3) collect console/warnings and post-process workspace scope variables.

## 1. Start MATLAB and share engine

In MATLAB command window:

```matlab
matlab.engine.shareEngine
```

## 2. Start your control kernel manually

This helper does not start or manage your kernel process.

## 3. Prepare channel mapping JSON

Use [scope_channel_map.example.json](scope_channel_map.example.json) as template.

Example:

```json
{
  "ScopeData1": ["speed_ref", "speed_fb"],
  "ScopeData2": ["iq_ref", "iq_fb"],
  "ScopeData3": ["torque", "dc_bus_voltage"],
  "ScopeData5": []
}
```

## 4. Run simulation from Python

```powershell
python agent_silhelper/run_local_job.py \
  --model-path "D:/WorkDocuments/Github/gmp_pro/ctl/suite/mcs_pmsm_nt/project/simulate/MCS_STD_PMSM_MODEL_2022b.slx" \
  --scope-map "agent_silhelper/scope_channel_map.example.json" \
  --scope-vars ScopeData1 ScopeData2 ScopeData3 ScopeData5 \
  --output "agent_silhelper/run_result.json"
```

## Output format

Main fields in output JSON:

- status
- diagnostics.error_msg
- diagnostics.matlab_console
- diagnostics.matlab_lastwarn_msg
- diagnostics.matlab_lastwarn_id
- signals.speed_ref / signals.speed_fb / ...
- raw_scopes (original decoded scope object)
- scope_mapping_errors

## Notes

- If a scope variable is `timeseries`, `Dataset`, or `struct`, script attempts automatic conversion.
- If one scope contains Nx2 matrix in a single entry, script auto-splits to two channels.
- If semantic names are missing, fallback names use `ScopeName.chN`.
- If the variable is not found in base workspace, the script also checks `out`.
