"""The analyses as callable tools. Used by the REST endpoints and by the chat layer (same code path)."""
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlencode

from pydantic import BaseModel

from ..analysis.considerations import evaluate
from ..analysis.errors import NoDataError
from ..analysis.models import (
    CompareResponse,
    CoverageResponse,
    EventsResponse,
    Pm25Response,
    Reproducible,
    StationsResponse,
    TimeseriesResponse,
    TrendResponse,
    WeekdayResponse,
)
from ..analysis.service import Pm25Service
from ..integrations.pdok import GeocodeError, geocode
from ..integrations.r_bridge import RError
from .responses import Candidate, GeocodeResponse
from .schemas import (
    CompareRequest,
    CoverageRequest,
    EventsRequest,
    GeocodeRequest,
    Pm25Request,
    StationsRequest,
    TimeseriesRequest,
    TrendRequest,
    WeekdayRequest,
)


class ToolError(Exception):
    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status, self.detail = status, detail


@dataclass(frozen=True)
class Tool:
    name: str
    path: str
    model: type[BaseModel]               # request
    response: type[Reproducible]
    run: Callable[[Pm25Service, BaseModel], Reproducible]

    @property
    def description(self) -> str:
        return (self.model.__doc__ or "").strip()


def _compare(s: Pm25Service, p: CompareRequest) -> CompareResponse:
    if p.against not in s.guidelines:
        raise ToolError(422, f"Unknown level set '{p.against}'; available: {sorted(s.guidelines)}")
    return s.compare(p.lat, p.lon, p.start, p.end, p.against, p.radius_km, p.cutoff, p.min_hours)


def _geocode(s: Pm25Service, p: GeocodeRequest) -> GeocodeResponse:
    candidates = [Candidate(**c) for c in geocode(p.q, p.limit)]
    facts = {"place_query": p.q, "place_candidates": len(candidates),
             "place_chosen": candidates[0].name if candidates else None,
             "place_alternatives": "; ".join(c.name for c in candidates[1:])}
    considerations = evaluate(s.rules, facts, scope="place")
    return GeocodeResponse(
        source="PDOK Locatieserver", chosen=candidates[0] if candidates else None, candidates=candidates,
        considerations=considerations, limitations=[c.message for c in considerations])


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("geocode", "/geocode", GeocodeRequest, GeocodeResponse, _geocode),
    Tool("coverage", "/coverage", CoverageRequest, CoverageResponse, lambda s, p: s.coverage()),
    Tool("stations", "/stations", StationsRequest, StationsResponse, lambda s, p: s.stations(p.lat, p.lon, p.radius_km)),
    Tool("pm25", "/pm25", Pm25Request, Pm25Response,
         lambda s, p: s.compute(p.lat, p.lon, p.date, p.radius_km, p.cutoff, p.min_hours)),
    Tool("pm25_timeseries", "/pm25/timeseries", TimeseriesRequest, TimeseriesResponse,
         lambda s, p: s.timeseries(p.lat, p.lon, p.start, p.end, p.resolution, p.radius_km, p.cutoff, p.min_hours)),
    Tool("pm25_compare", "/pm25/compare", CompareRequest, CompareResponse, _compare),
    Tool("pm25_weekday", "/pm25/weekday", WeekdayRequest, WeekdayResponse,
         lambda s, p: s.weekday(p.lat, p.lon, p.start, p.end, p.radius_km, p.cutoff, p.min_hours)),
    Tool("pm25_trend", "/pm25/trend", TrendRequest, TrendResponse,
         lambda s, p: s.trend(p.lat, p.lon, p.start, p.end, p.radius_km, p.cutoff, p.min_hours)),
    Tool("pm25_events", "/pm25/events", EventsRequest, EventsResponse,
         lambda s, p: s.events(p.lat, p.lon, p.start, p.end, p.threshold, p.radius_km, p.cutoff, p.min_hours)),
]}


def execute(service: Pm25Service, tool: Tool, params: BaseModel) -> dict:
    """Run a tool and return its response as a JSON-ready dict.

    The response gets `request` (resolved parameters) and `reproduce` (a URL that reruns it).
    """
    try:
        result = tool.run(service, params)
    except NoDataError as exc:
        raise ToolError(404, {"message": str(exc), "audit": exc.audit}) from exc
    except (RError, GeocodeError) as exc:
        raise ToolError(503, str(exc)) from exc
    request = params.model_dump(by_alias=True, mode="json")
    result = result.model_copy(update={
        "request": request, "reproduce": f"{tool.path}?{urlencode(request)}" if request else tool.path})
    return result.model_dump(by_alias=True, mode="json")
