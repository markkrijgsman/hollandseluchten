"""LLM clients: Claude (Anthropic), OpenAI, or the rule-based stub when there is no API key."""
import json
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


class OpenAILLM:
    """Wraps the OpenAI chat-completions API in the Anthropic content-block protocol used by the engine."""

    def __init__(self, model: str | None = None):
        from openai import OpenAI
        self.client = OpenAI()
        self.model = model or os.environ.get("HL_CHAT_MODEL", "gpt-4o")
        self.name = self.model

    def create(self, *, system, messages, tools):
        oai_tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}}
            for t in tools
        ]
        oai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if isinstance(content, str):
                oai_messages.append({"role": role, "content": content})
            elif isinstance(content, list):
                if role == "assistant":
                    text = "".join(b["text"] for b in content if b["type"] == "text")
                    calls = [
                        {"id": b["id"], "type": "function",
                         "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                        for b in content if b["type"] == "tool_use"
                    ]
                    oai_messages.append({"role": "assistant", "content": text or None,
                                         "tool_calls": calls or None})
                else:
                    for b in content:
                        if b["type"] == "tool_result":
                            oai_messages.append({"role": "tool", "tool_call_id": b["tool_use_id"],
                                                 "content": b["content"]})

        resp = self.client.chat.completions.create(model=self.model, messages=oai_messages,
                                                   tools=oai_tools, max_tokens=1500)
        msg = resp.choices[0].message
        content = []
        if msg.content:
            content.append({"type": "text", "text": msg.content})
        for tc in (msg.tool_calls or []):
            content.append({"type": "tool_use", "id": tc.id, "name": tc.function.name,
                            "input": json.loads(tc.function.arguments)})
        return {"content": content}


def get_llm() -> LLM:
    """HL_LLM selects the backend: 'openai', 'anthropic', or 'fake'. Auto-detects from API keys."""
    mode = os.environ.get("HL_LLM", "")
    if mode == "fake":
        from .fake_llm import FakeLLM
        return FakeLLM()
    if mode == "openai" or (mode != "anthropic" and os.environ.get("OPENAI_API_KEY")
                             and not os.environ.get("ANTHROPIC_API_KEY")):
        return OpenAILLM()
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicLLM()
    from .fake_llm import FakeLLM
    return FakeLLM()
