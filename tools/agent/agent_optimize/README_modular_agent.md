# Modular Motor Simulation Agent

This package is a refactored version of `agent_modified.py`.

## Directory layout

```text
agent_modified.py                  # Thin entry point
agent_project.json                 # Existing config, relative paths preserved
build_sln.bat                      # Compile only
start_exe.bat                      # Start generated exe
agent_core/
  app.py                           # Interactive loop and tool-call loop
  config.py                        # Project config and relative path resolution
  constants.py                     # Shared constants
  llm.py                           # DeepSeek/OpenAI-compatible client
  prompts.py                       # System prompt
  process_runner.py                # Safe .bat process launcher
  tool_registry.py                 # Tool schema + handler registry
  utils.py                         # File reading, truncation, timestamp helpers
  tools/
    resources.py                   # list/read resource tools
    automation.py                  # build/start exe/run simulink closed loop tools
```

## Why this split helps

- Add a write/patch tool by creating `agent_core/tools/file_patch.py` and registering it in `app.py`.
- Add a teammate knowledge base tool by creating `agent_core/tools/knowledge_base.py`.
- Keep the main interaction loop unchanged while expanding capabilities.
- Keep all shell/bat execution in `process_runner.py` and `automation.py`, rather than letting the model execute arbitrary commands.

## Run

Place this package in:

```text
工程文件夹/tools/agent/agent_optimize/
```

Then run:

```bat
python agent_modified.py
```

## Existing JSON compatibility

The code uses your current `agent_project.json` fields:

```json
"build_bat_path": "build_sln.bat",
"start_exe_bat_path": "start_exe.bat",
"sim_bat_path": "../agent_silhelper/run_local_quick.bat",
"build_agent_log": "../log/build.log",
"run_exe_log": "../log/run_exe.log",
"simulation_result": "../log/processed.json"
```

All relative paths are resolved relative to `agent_project.json`.
