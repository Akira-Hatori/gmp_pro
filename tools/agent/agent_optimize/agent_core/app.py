import json
from typing import Any, Dict, List


from .config import load_project_context
from .llm import LLMClient
from .prompts import SYSTEM_PROMPT
from .tool_registry import ToolRegistry
from .tools import (
    register_automation_tools,
    register_resource_tools,
    register_evaluation_tools,
    register_parameter_edit_tools,
    register_optimization_tools,
)


def build_registry(ctx) -> ToolRegistry:
    registry = ToolRegistry()
    register_resource_tools(registry, ctx)
    register_automation_tools(registry, ctx)
    register_evaluation_tools(registry, ctx)
    register_parameter_edit_tools(registry, ctx)
    register_optimization_tools(registry, ctx)
    return registry


def _message_to_dict(message: Any) -> Dict[str, Any]:
    """Keep OpenAI-compatible message objects usable in the local conversation list."""
    # The OpenAI SDK message object already works in many cases, but dict conversion is more robust
    # when appending it back into the messages list.
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    if isinstance(message, dict):
        return message
    return {
        "role": getattr(message, "role", "assistant"),
        "content": getattr(message, "content", None),
        "tool_calls": getattr(message, "tool_calls", None),
    }


def interactive_loop(llm: LLMClient, registry: ToolRegistry) -> None:
    print("Motor Agent started. Type exit to quit.")
    print("Try: list available project resources")
    print("Try: run one closed-loop build and simulation")
    print("Try: read simulation_result and summarize its JSON structure")
    print("Try: build solution")
    print("Try: start exe")
    print("Try: run simulink simulation")
    print("Try: list project_src")

    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    while True:
        user_input = input("\nUser> ").strip()
        if user_input.lower() in {"exit", "quit"}:
            print("Agent exited.")
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        while True:
            assistant_message = llm.ask(messages, registry.schemas())
            assistant_dict = _message_to_dict(assistant_message)
            messages.append(assistant_dict)

            tool_calls = assistant_dict.get("tool_calls") or []
            if not tool_calls:
                print(f"\nAgent> {assistant_dict.get('content')}")
                break

            for tool_call in tool_calls:
                function = tool_call.get("function", {}) if isinstance(tool_call, dict) else tool_call.function
                if isinstance(function, dict):
                    function_name = function.get("name")
                    raw_arguments = function.get("arguments") or "{}"
                    tool_call_id = tool_call.get("id")
                else:
                    function_name = function.name
                    raw_arguments = function.arguments or "{}"
                    tool_call_id = tool_call.id

                try:
                    function_args = json.loads(raw_arguments)
                except json.JSONDecodeError as exc:
                    function_args = {}
                    tool_result = f"Error: invalid tool arguments JSON: {exc}\nraw_arguments={raw_arguments}"
                else:
                    print(f"\n[tool call] {function_name}({function_args})")
                    tool_result = registry.run(function_name, function_args)

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": tool_result,
                    }
                )


def main() -> None:
    ctx = load_project_context()
    llm = LLMClient(ctx)
    registry = build_registry(ctx)
    interactive_loop(llm, registry)
