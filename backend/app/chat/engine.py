"""Chat layer: a question goes to an LLM that can only call the analysis tools; the server runs them.

The LLM never computes numbers. Every tool call and its full result (with audit) is returned to the client.
Stateless: the client sends `history` back with each request.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from pydantic import BaseModel, ValidationError

from ..analysis.service import Pm25Service
from ..tools.registry import TOOLS, ToolError, execute
from .llm import LLM
from .prompt import SYSTEM_PROMPT

MAX_STEPS = 6
MAX_MODEL_SERIES_POINTS = 31



class ChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = []


def tool_specs() -> list[dict]:
    return [{"name": t.name, "description": t.description,
             "input_schema": t.model.model_json_schema(by_alias=True)} for t in TOOLS.values()]


def _for_model(envelope: dict) -> dict:
    """What the LLM sees: no audit, and long series replaced by the summary (the client gets everything)."""
    out = {k: v for k, v in envelope.items() if k != "audit"}
    series = out.get("series")
    if series and len(series) > MAX_MODEL_SERIES_POINTS:
        out["series"] = f"{len(series)} points omitted; use summary"
    return out


def _run_tool(service: Pm25Service, name: str, args: dict) -> tuple[dict | None, str]:
    """Returns (full envelope or None, text for the model)."""
    tool = TOOLS.get(name)
    if tool is None:
        return None, f"Unknown tool '{name}'"
    try:
        params = tool.model.model_validate(args)
    except ValidationError as exc:
        return None, "Invalid input: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())
    try:
        envelope = execute(service, tool, params)
    except ToolError as exc:
        detail = exc.detail["message"] if isinstance(exc.detail, dict) else exc.detail
        return None, f"Error {exc.status}: {detail}"
    return envelope, json.dumps(_for_model(envelope), default=str)


def chat(service: Pm25Service, llm: LLM, req: ChatRequest) -> dict:
    messages = [*req.history, {"role": "user", "content": req.message}]
    system = SYSTEM_PROMPT.format(today=date.today().isoformat())
    tools = tool_specs()
    interpretation, results, finished = [], [], False
    for _ in range(MAX_STEPS):
        content = llm.create(system=system, messages=messages, tools=tools)["content"]
        messages.append({"role": "assistant", "content": content})
        uses = [b for b in content if b["type"] == "tool_use"]
        if not uses:
            finished = True
            break
        blocks = []
        for use in uses:
            envelope, text = _run_tool(service, use["name"], use["input"])
            call = {"tool": use["name"], "input": use["input"]}
            if envelope:
                results.append(envelope)
                call["reproduce"] = envelope["reproduce"]
            else:
                call["error"] = text
            interpretation.append(call)
            blocks.append({"type": "tool_result", "tool_use_id": use["id"], "content": text,
                           **({} if envelope else {"is_error": True})})
        messages.append({"role": "user", "content": blocks})
    answer = "".join(b["text"] for b in messages[-1]["content"] if b["type"] == "text") if finished else ""
    if not answer:
        answer = "I could not complete this analysis. Please rephrase or narrow the question."
    called_tools = {c["tool"] for c in interpretation if "error" not in c}
    return {
        "answer": answer,
        # no analysis ran and the model replied: it is asking the resident something
        "clarifying_question": answer if finished and not results else None,
        "interpretation": interpretation, "results": results,
        "suggestions": _suggestions(called_tools),
        "llm": llm.name, "history": messages,
    }


def _suggestions(called: set[str]) -> list[str]:
    if "pm25_compare" in called:
        return ["Show how it changed per day", "What are the nearest measuring stations?"]
    if "pm25_timeseries" in called:
        return ["How does this compare with the WHO guideline?"]
    if "pm25" in called:
        return ["How did the whole year compare with the WHO guideline?", "Show the trend over that month"]
    return []
