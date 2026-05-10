import os
from typing import Any, Dict, List

from dotenv import load_dotenv
from openai import OpenAI

from .config import ProjectContext


class LLMClient:
    def __init__(self, ctx: ProjectContext) -> None:
        load_dotenv(dotenv_path=ctx.env_path, override=True, encoding="utf-8-sig")
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError(
                f"DEEPSEEK_API_KEY was not found.\n"
                f"Please check .env path: {ctx.env_path}\n"
                f"Expected format: DEEPSEEK_API_KEY=sk-your-key"
            )
        self.model = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")

    def ask(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Any:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            stream=False,
        )
        return response.choices[0].message
