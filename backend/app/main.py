"""REST API. Every endpoint validates its query with a model from tools/schemas.py and runs the matching tool."""
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .analysis.models import CompareResponse, CoverageResponse, Pm25Response, StationsResponse, TimeseriesResponse
from .analysis.service import Pm25Service
from .chat import LLM, ChatRequest, get_llm
from .chat import chat as run_chat
from .settings import Settings
from .tools.registry import TOOLS, ToolError, execute
from .tools.responses import GeocodeResponse
from .tools.schemas import (
    CompareRequest,
    CoverageRequest,
    GeocodeRequest,
    Pm25Request,
    StationsRequest,
    TimeseriesRequest,
)

DESCRIPTION = """
Air-pollution (PM2.5) answers for residents, with a transparent audit trail.

* **Analysis endpoints** (`/geocode`, `/coverage`, `/stations`, `/pm25`, `/pm25/timeseries`, `/pm25/compare`) are
  deterministic. Every response has `limitations`, an `audit` list of the steps taken, the resolved `request`
  and a `reproduce` URL that reruns the analysis.
* **`POST /chat`** lets an LLM translate a question into calls on those endpoints. The model never computes numbers.
  The response lists every call made (`interpretation`) and the full results including their audit.
  Without `ANTHROPIC_API_KEY` a rule-based stub answers (see the `llm` field in the response).
"""

app = FastAPI(title="Hollandse Luchten PM2.5 API", description=DESCRIPTION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@lru_cache
def get_service() -> Pm25Service:
    return Pm25Service(Settings.from_env())


def run(name: str, params, service: Pm25Service) -> dict:
    try:
        return execute(service, TOOLS[name], params)
    except ToolError as exc:
        raise HTTPException(exc.status, exc.detail) from exc


Service = Annotated[Pm25Service, Depends(get_service)]


@app.get("/geocode", response_model=GeocodeResponse, description=TOOLS["geocode"].description)
def geocode(p: Annotated[GeocodeRequest, Query()], service: Service):
    return run("geocode", p, service)


@app.get("/coverage", response_model=CoverageResponse, description=TOOLS["coverage"].description)
def coverage(p: Annotated[CoverageRequest, Query()], service: Service):
    return run("coverage", p, service)


@app.get("/stations", response_model=StationsResponse, description=TOOLS["stations"].description)
def stations(p: Annotated[StationsRequest, Query()], service: Service):
    return run("stations", p, service)


@app.get("/pm25", response_model=Pm25Response, description=TOOLS["pm25"].description)
def pm25(p: Annotated[Pm25Request, Query()], service: Service):
    return run("pm25", p, service)


@app.get("/pm25/timeseries", response_model=TimeseriesResponse, description=TOOLS["pm25_timeseries"].description)
def pm25_timeseries(p: Annotated[TimeseriesRequest, Query()], service: Service):
    return run("pm25_timeseries", p, service)


@app.get("/pm25/compare", response_model=CompareResponse, description=TOOLS["pm25_compare"].description)
def pm25_compare(p: Annotated[CompareRequest, Query()], service: Service):
    return run("pm25_compare", p, service)


@app.post("/chat", description="Ask a question in plain language. Send the returned `history` back with the next message for follow-ups.")
def chat(req: ChatRequest, service: Service, llm: Annotated[LLM, Depends(get_llm)]):
    return run_chat(service, llm, req)
