"""The analyses as callable tools. Used by the REST endpoints and by the chat layer (same code path)."""
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode

from pydantic import BaseModel

from ..integrations.pdok import GeocodeError, geocode
from ..integrations.r_bridge import RError
from .schemas import (CompareRequest, CoverageRequest, GeocodeRequest, Pm25Request, StationsRequest,
                      TimeseriesRequest)
from ..analysis.errors import NoDataError
from ..analysis.service import Pm25Service


class ToolError(Exception):
    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status, self.detail = status, detail


@dataclass(frozen=True)
class Tool:
    name: str
    path: str
    model: type[BaseModel]
    run: Callable[[Pm25Service, BaseModel], dict]

    @property
    def description(self) -> str:
        return (self.model.__doc__ or "").strip()


def _compare(s: Pm25Service, p: CompareRequest) -> dict:
    if p.against not in s.guidelines:
        raise ToolError(422, f"Unknown level set '{p.against}'; available: {sorted(s.guidelines)}")
    return s.compare(p.lat, p.lon, p.start, p.end, p.against, p.radius_km, p.cutoff, p.min_hours)


def _geocode(_: Pm25Service, p: GeocodeRequest) -> dict:
    return {"source": "PDOK Locatieserver", "candidates": geocode(p.q, p.limit),
            "limitations": ["Several candidates means the query is ambiguous: ask the user which one is meant."]}


TOOLS: dict[str, Tool] = {t.name: t for t in [
    Tool("geocode", "/geocode", GeocodeRequest, _geocode),
    Tool("coverage", "/coverage", CoverageRequest, lambda s, p: s.coverage()),
    Tool("stations", "/stations", StationsRequest, lambda s, p: s.stations(p.lat, p.lon, p.radius_km)),
    Tool("pm25", "/pm25", Pm25Request,
         lambda s, p: s.compute(p.lat, p.lon, p.date, p.radius_km, p.cutoff, p.min_hours)),
    Tool("pm25_timeseries", "/pm25/timeseries", TimeseriesRequest,
         lambda s, p: s.timeseries(p.lat, p.lon, p.start, p.end, p.resolution, p.radius_km, p.cutoff, p.min_hours)),
    Tool("pm25_compare", "/pm25/compare", CompareRequest, _compare),
]}


def execute(service: Pm25Service, tool: Tool, params: BaseModel) -> dict:
    """Run a tool. The result gets `request` (resolved parameters) and `reproduce` (URL that reruns it)."""
    try:
        result = tool.run(service, params)
    except NoDataError as exc:
        raise ToolError(404, {"message": str(exc), "audit": exc.audit}) from exc
    except (RError, GeocodeError) as exc:
        raise ToolError(503, str(exc)) from exc
    request = params.model_dump(by_alias=True, mode="json")
    return {**result, "request": request, "reproduce": f"{tool.path}?{urlencode(request)}" if request else tool.path}
