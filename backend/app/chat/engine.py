"""Chat layer: a question goes to an LLM agent that can only call the analysis tools; the server runs them.

The LLM never computes numbers. Every tool call and its full result (with audit) is returned to the client.
Stateless: the client sends `history` back with each request.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
    messages_from_dict,
    messages_to_dict,
)
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel

from ..analysis.service import Pm25Service
from .prompt import SYSTEM_PROMPT
from .tools import build_tools

MAX_STEPS = 6  # model calls per question


class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


def _load_history(history: list[dict]) -> list[BaseMessage]:
    """Accepts what this API returned, or plain {role, content} turns."""
    out: list[BaseMessage] = []
    for h in history:
        if "type" in h:
            out += messages_from_dict([h])
        elif h.get("role") in ("user", "assistant"):
            out.append((HumanMessage if h["role"] == "user" else AIMessage)(content=h["content"]))
    return out


def _text(message: BaseMessage) -> str:
    c = message.content
    return c if isinstance(c, str) else "".join(b.get("text", "") for b in c if isinstance(b, dict))


def chat(service: Pm25Service, model: BaseChatModel, req: ChatRequest) -> dict:
    prior = _load_history(req.history)
    agent = create_agent(model, build_tools(service), system_prompt=SYSTEM_PROMPT.format(today=date.today().isoformat()))
    state = {"messages": [*prior, HumanMessage(req.message)]}
    try:
        messages = agent.invoke(state, {"recursion_limit": 2 * MAX_STEPS + 1})["messages"]
        finished = True
    except GraphRecursionError:
        messages, finished = state["messages"], False

    new = messages[len(prior):]
    replies = {m.tool_call_id: m for m in new if isinstance(m, ToolMessage)}
    interpretation, results = [], []
    for m in new:
        for call in (m.tool_calls if isinstance(m, AIMessage) else []):
            entry = {"tool": call["name"], "input": call["args"]}
            reply = replies.get(call["id"])
            if reply is not None and reply.artifact:
                results.append(reply.artifact)
                entry["reproduce"] = reply.artifact["reproduce"]
            else:
                entry["error"] = str(reply.content) if reply is not None else "no result"
            interpretation.append(entry)

    last = new[-1] if new else None
    answer = _text(last) if finished and isinstance(last, AIMessage) and not last.tool_calls else ""
    if not answer:
        answer = "I could not complete this analysis. Please rephrase or narrow the question."
    called = {c["tool"] for c in interpretation if "error" not in c}
    return {
        "answer": answer,
        # no analysis ran and the model replied: it is asking the resident something
        "clarifying_question": answer if finished and not results and not interpretation else None,
        "interpretation": interpretation, "results": results,
        "suggestions": _suggestions(called),
        "llm": getattr(model, "model_name", None) or type(model).__name__,
        "history": messages_to_dict([_without_artifact(m) for m in messages]),
    }


def _without_artifact(m: BaseMessage) -> BaseMessage:
    """The full results go to the client once in `results`; they are not resent with every follow-up."""
    return m.model_copy(update={"artifact": None}) if isinstance(m, ToolMessage) else m


def _suggestions(called: set[str]) -> list[str]:
    if "pm25_compare" in called:
        return ["Show how it changed per day", "What are the nearest measuring stations?"]
    if "pm25_timeseries" in called:
        return ["How does this compare with the WHO guideline?"]
    if "pm25" in called:
        return ["How did the whole year compare with the WHO guideline?", "Show the trend over that month"]
    return []
