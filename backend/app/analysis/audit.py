"""The audit trail: an ordered list of typed steps taken for one request.

Every step has a `code` (stable, for clients), an `action` (readable name) and fields specific to the step type.
"""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_serializer


class AuditStep(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    step: int = Field(0, description="Position in the trail; set by AuditLog")
    action: str


class CompactStep(AuditStep):
    """A step whose empty (None) fields are left out of the JSON."""

    @model_serializer(mode="wrap")
    def _drop_none(self, handler):
        return {k: v for k, v in handler(self).items() if v is not None}


class RequestStep(CompactStep):
    code: Literal["request"] = "request"
    action: str = "request"
    lat: float
    lon: float
    date: str | None = None
    start: str | None = None
    end: str | None = None
    resolution: str | None = None
    radius_km: float
    outlier_cutoff: float
    min_hours_per_station: int
    day_definition: str


class SelectStationsStep(CompactStep):
    code: Literal["select_stations"] = "select_stations"
    kind: Literal["reference", "sensor"]
    source: str | None = None
    stations: list[str] = []
    station_types: dict[str, str] | None = Field(None, description="Official stations: station -> type")
    note: str | None = None
    skipped: bool | None = None
    reason: str | None = None


class RFunctionsStep(CompactStep):
    code: Literal["r_functions"] = "r_functions"
    action: str = "R: Analyse-Together functions"
    functions: list[str] = Field(description="Functions R reports it applied, in order")
    parameters: dict[str, float] = Field(description="Parameters R reports it used")
    hourly_values_in: int
    outliers_removed: int


class StationMeansStep(CompactStep):
    code: Literal["station_means"] = "station_means"
    station_periods_used: int
    station_periods_excluded_for_too_few_hours: int
    excluded_for_too_few_hours: dict[str, int] | None = Field(None, description="Single period only: station -> hours")


class WeightedMeanStep(CompactStep):
    code: Literal["weighted_mean"] = "weighted_mean"
    weights: str
    basis: str | None = None
    result: float | None = None
    periods: int | None = None
    periods_from_sensors: int | None = None


class CompareStep(CompactStep):
    code: Literal["compare"] = "compare"
    action: str = "compare with reference levels"
    against: str
    levels: list[dict[str, Any]]


class WeekdaySplitStep(CompactStep):
    code: Literal["weekday_split"] = "weekday_split"
    action: str = "weekday vs weekend split"
    weekday_days: int
    weekend_days: int
    weekday_mean: float | None = None
    weekend_mean: float | None = None
    difference: float | None = None


class TrendStep(CompactStep):
    code: Literal["linear_trend"] = "linear_trend"
    action: str = "linear trend"
    slope_ug_m3_per_day: float
    direction: str
    stable_below: float = Field(description="Slopes smaller than this (ug/m3 per day) count as stable")
    n_points: int


class EventsStep(CompactStep):
    code: Literal["events_above_threshold"] = "events_above_threshold"
    action: str = "events above threshold"
    threshold: float
    n_events: int
    n_days_with_data: int
    share_above: float


class VersionsStep(AuditStep):
    """Which code and data produced the result (informational). Fields come from versions.py."""
    model_config = ConfigDict(extra="allow")
    code: Literal["versions"] = "versions"
    action: str = "versions"


AuditStepT = Annotated[
    RequestStep | SelectStationsStep | RFunctionsStep | StationMeansStep | WeightedMeanStep | CompareStep
    | WeekdaySplitStep | TrendStep | EventsStep | VersionsStep, Field(discriminator="code")]


class AuditLog:
    def __init__(self) -> None:
        self.steps: list[AuditStep] = []

    def log(self, step: AuditStep) -> None:
        step.step = len(self.steps) + 1
        self.steps.append(step)

    def as_dicts(self) -> list[dict]:
        return [s.model_dump(mode="json") for s in self.steps]
