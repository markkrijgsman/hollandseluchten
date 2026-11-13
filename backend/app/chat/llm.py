"""LLM clients: Claude through the Anthropic SDK, or the rule-based stub when there is no API key."""
from __future__ import annotations

import os
from typing import Protocol


class LLM(Protocol):
    name: str

    def create(self, *, system: str, messages: list[dict], tools: list[dict]) -> dict:
        """Return {"content": [text / tool_use blocks as dicts]}."""


class AnthropicLLM:
    def __init__(self, model: str | None = None):
        import anthropic
        self.client = anthropic.Anthropic()
        self.model = model or os.environ.get("HL_CHAT_MODEL", "claude-sonnet-5-5")
        self.name = self.model

    def create(self, *, system, messages, tools):
        resp = self.client.messages.create(model=self.model, max_tokens=1500, system=system,
                                           messages=messages, tools=tools)
        return {"content": [b.model_dump(exclude_none=True) for b in resp.content
                            if b.type in ("text", "tool_use")]}


def get_llm() -> LLM:
    """HL_LLM=fake forces the rule-based stub; otherwise Claude when ANTHROPIC_API_KEY is set, else the stub."""
    mode = os.environ.get("HL_LLM", "")
    if mode == "fake" or (mode != "anthropic" and not os.environ.get("ANTHROPIC_API_KEY")):
        from .fake_llm import FakeLLM
        return FakeLLM()
    return AnthropicLLM()
