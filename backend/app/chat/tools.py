"""The analysis tools (app/tools/registry.py) as LangChain tools.

Each tool returns two things: text for the model (no audit, long series summarised) and the full envelope as
`artifact`, which the client gets. Input validation stays with the request models, so a bad call comes back to
the model as an error text it can correct.
"""
import json

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import ValidationError

from ..analysis.service import Pm25Service
from ..tools.registry import TOOLS, Tool, ToolError, execute

MAX_MODEL_SERIES_POINTS = 31
ERROR_PREFIXES = ("Error ", "Invalid input", "Unknown tool")


def for_model(envelope: dict) -> dict:
    """What the LLM sees: no audit, and long series replaced by the summary (the client gets everything)."""
    out = {k: v for k, v in envelope.items() if k != "audit"}
    series = out.get("series")
    if series and len(series) > MAX_MODEL_SERIES_POINTS:
        out["series"] = f"{len(series)} points omitted; use summary"
    return out


def run_tool(service: Pm25Service, tool: Tool, args: dict) -> tuple[str, dict | None]:
    """Returns (text for the model, full envelope or None on error)."""
    try:
        params = tool.model.model_validate(args)
    except ValidationError as exc:
        return "Invalid input: " + "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()), None
    try:
        envelope = execute(service, tool, params)
    except ToolError as exc:
        detail = exc.detail["message"] if isinstance(exc.detail, dict) else exc.detail
        return f"Error {exc.status}: {detail}", None
    return json.dumps(for_model(envelope), default=str), envelope


def is_error(text: str) -> bool:
    return text.startswith(ERROR_PREFIXES)


def build_tools(service: Pm25Service) -> list[BaseTool]:
    def build(tool: Tool) -> BaseTool:
        def call(**kwargs) -> tuple[str, dict | None]:
            return run_tool(service, tool, kwargs)

        return StructuredTool(
            name=tool.name, description=tool.description, func=call, response_format="content_and_artifact",
            # a JSON schema (with the 'from'/'to' aliases) goes to the model; validation happens in run_tool
            args_schema=tool.model.model_json_schema(by_alias=True))

    return [build(t) for t in TOOLS.values()]
