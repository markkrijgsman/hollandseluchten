"""Chat models: OpenAI through LangChain, or the rule-based stub when there is no API key."""
import os
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .fake_llm import FakeLLM
from .tools import is_error


def get_chat_model() -> BaseChatModel:
    """HL_LLM=fake forces the stub; HL_LLM=openai forces OpenAI. By default OpenAI is used when OPENAI_API_KEY is set."""
    mode = os.environ.get("HL_LLM", "")
    if mode == "fake" or (mode != "openai" and not os.environ.get("OPENAI_API_KEY")):
        return FakeChatModel()
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(model=os.environ.get("HL_CHAT_MODEL", "gpt-4o"), temperature=0)


class FakeChatModel(BaseChatModel):
    """Adapts the rule-based FakeLLM to LangChain, so the same agent runs with and without an API key."""

    @property
    def _llm_type(self) -> str:
        return "fake"

    @property
    def model_name(self) -> str:
        return FakeLLM.name

    def bind_tools(self, tools, **kwargs):
        return self  # the stub knows its tools

    def _generate(self, messages: list[BaseMessage], stop=None, run_manager=None, **kwargs: Any) -> ChatResult:
        system = next((m.content for m in messages if isinstance(m, SystemMessage)), "")
        out = FakeLLM().create(system=str(system), messages=_to_blocks(messages), tools=[])["content"]
        text = "".join(b["text"] for b in out if b["type"] == "text")
        calls = [{"name": b["name"], "args": b["input"], "id": b["id"], "type": "tool_call"}
                 for b in out if b["type"] == "tool_use"]
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text, tool_calls=calls))])


def _to_blocks(messages: list[BaseMessage]) -> list[dict]:
    """LangChain messages -> the block protocol that FakeLLM speaks."""
    out: list[dict] = []
    for m in messages:
        if isinstance(m, HumanMessage):
            out.append({"role": "user", "content": str(m.content)})
        elif isinstance(m, AIMessage):
            blocks = ([{"type": "text", "text": str(m.content)}] if m.content else []) + [
                {"type": "tool_use", "id": c["id"], "name": c["name"], "input": c["args"]} for c in m.tool_calls]
            out.append({"role": "assistant", "content": blocks})
        elif isinstance(m, ToolMessage):
            block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": str(m.content),
                     **({"is_error": True} if is_error(str(m.content)) else {})}
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
    return out
