"""Typed results of the analyses. They are the response schema of the API (and what Swagger documents)."""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Basis = Literal["sensors", "reference_stations"]


class Model(BaseModel):
    model_config = ConfigDict(populate_by_name=True)


class Reproducible(Model):
    """Set by the tool layer: the resolved request and a URL that reruns it."""
    request: dict[str, Any] | None = None
    reproduce: str | None = None


class AuditStep(Model):
    """One step of the audit trail. Steps carry action-specific details as extra fields."""
    model_config = ConfigDict(extra="allow")
    step: int
    action: str


class Location(Model):
    lat: float
    lon: float


class StationEstimate(Model):
    id: str
    name: str
    distance_km: float
    weight: float = Field(description="Share of this station in the weighted mean of its source type")
    daily_mean: float
    uncertainty: float
    valid_hours: int


class SourceEstimate(Model):
    pm25_ug_m3: float
    uncertainty_ug_m3: float
    stations: list[StationEstimate]


class Pm25Response(Reproducible):
    date: str
    location: Location
    radius_km: float
    unit: str
    pm25: float = Field(description="Distance-weighted daily mean, ug/m3")
    uncertainty: float
    basis: Basis
    sensors: SourceEstimate | None
    reference: SourceEstimate | None
    limitations: list[str]
    audit: list[AuditStep]


class SeriesPoint(Model):
    time: str = Field(description="YYYY-MM-DD, or YYYY-MM-DDTHH (fixed UTC+1) for hourly")
    pm25: float
    uncertainty: float
    basis: Basis
    stations_used: int


class SeriesSummary(Model):
    periods_with_data: int
    periods_expected: int
    mean: float
    min: float
    max: float


class TimeseriesResponse(Reproducible):
    location: Location
    radius_km: float
    resolution: Literal["day", "hour"]
    unit: str
    series: list[SeriesPoint]
    summary: SeriesSummary
    limitations: list[str]
    audit: list[AuditStep]


class Level(Model):
    id: str
    name: str
    type: Literal["daily", "annual"]
    limit: float
    source: str
    verified: bool = Field(description="False: the value was not checked against its source")


class DailyComparison(Level):
    type: Literal["daily"]
    days_with_data: int
    days_above: int
    share_above: float
    days_above_even_at_lower_bound: int
    days_above_at_upper_bound: int


class AnnualComparison(Level):
    type: Literal["annual"]
    period_mean: float
    uncertainty: float
    exceeded: bool
    uncertain: bool = Field(description="The mean is within its uncertainty of the limit")


class CompareResponse(Reproducible):
    location: Location
    radius_km: float
    unit: str
    against: str
    comparisons: list[DailyComparison | AnnualComparison]
    summary: SeriesSummary
    limitations: list[str]
    audit: list[AuditStep]


class SourceCoverage(Model):
    from_: str = Field(alias="from")
    to: str
    stations: int


class CoverageResponse(Reproducible):
    unit: str
    day_definition: str
    reference_stations: SourceCoverage
    sensors: SourceCoverage | None
    guideline_sets: list[str]
    versions: dict[str, Any]
    limitations: list[str]


class StationInfo(Model):
    id: str
    name: str
    kind: Literal["reference", "sensor"]
    distance_km: float
    lat: float
    lon: float
    station_type: str | None
    area_type: str | None
    data_from: str
    data_to: str


class StationsResponse(Reproducible):
    location: Location
    radius_km: float
    count: int
    stations: list[StationInfo]
    limitations: list[str]
