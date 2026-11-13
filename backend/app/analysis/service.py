"""Facade over the analyses. Each method builds one response; the work is done by the modules it composes."""
from datetime import date as Date
from functools import cached_property

from ..data.repositories import ReferenceRepository, SensorRepository
from ..settings import Settings
from . import weighting
from .audit import AuditLog, CompareStep, RequestStep, VersionsStep, WeightedMeanStep
from .catalog import Catalog
from .compare import compare_with_levels
from .considerations import evaluate, load_rules
from .constants import BASIS, DAY_DEFINITION, REFERENCE, SENSOR, UNIT, WEIGHT_FORMULA
from .guidelines import load_guidelines
from .models import (
    CompareResponse,
    Consideration,
    CoverageResponse,
    EventDay,
    EventsResponse,
    GuidelinesNorms,
    Location,
    Pm25Response,
    SeriesPoint,
    SeriesSummary,
    SourceEstimate,
    StationsResponse,
    TimeseriesResponse,
    TrendResponse,
    WeekdayGroup,
    WeekdayResponse,
)
from .observations import ObservationLoader
from .periods import RESOLUTIONS
from .pipeline import Pipeline
from .versions import collect_versions


def _slope(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    sx, sy = sum(xs), sum(ys)
    sxy = sum(x * y for x, y in zip(xs, ys))
    sxx = sum(x * x for x in xs)
    denom = n * sxx - sx * sx
    return (n * sxy - sx * sy) / denom if denom else 0.0


class Pm25Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reference = ReferenceRepository(settings.reference_measurements, settings.reference_metadata)
        self.sensors = SensorRepository(settings.sensor_parquet) if settings.sensor_parquet else None
        self.guidelines = load_guidelines()
        self.rules = load_rules()
        self._pipeline = Pipeline(ObservationLoader(settings, self.reference, self.sensors))
        self._catalog = Catalog(self.reference, self.sensors)

    @cached_property
    def versions(self) -> dict:
        return collect_versions(self.settings, self.reference, self.sensors)

    def compute(self, lat: float, lon: float, day: Date, radius_km: float = 5.0,
                cutoff: float = 100.0, min_hours: int = 18) -> Pm25Response:
        """Distance-weighted daily mean at a point, with the per-station breakdown."""
        audit = AuditLog()
        audit.log(RequestStep(lat=lat, lon=lon, date=day.isoformat(), radius_km=radius_km, outlier_cutoff=cutoff,
                              min_hours_per_station=min_hours, day_definition=DAY_DEFINITION))
        result = self._pipeline.run(audit, lat, lon, day, day, "day", radius_km, cutoff, min_hours)

        period = day.isoformat()
        by_kind = {}
        for kind in (SENSOR, REFERENCE):
            if (period, kind) in result.estimates.index:
                est = result.estimates.loc[(period, kind)]
                by_kind[kind] = SourceEstimate(
                    pm25_ug_m3=round(float(est["pm25"]), 2), uncertainty_ug_m3=round(float(est["uncertainty"]), 2),
                    stations=weighting.station_breakdown(result.per[result.per["kind"] == kind]))
        chosen_kind = result.chosen.loc[period, "kind"]
        basis, estimate = BASIS[chosen_kind], by_kind[chosen_kind]
        audit.log(WeightedMeanStep(action="distance-weighted mean", weights=WEIGHT_FORMULA,
                                   basis=result.facts["basis"], result=estimate.pm25_ug_m3))
        audit.log(VersionsStep(**self.versions))
        considerations = evaluate(self.rules, result.facts)
        return Pm25Response(
            date=period, location=Location(lat=lat, lon=lon), radius_km=radius_km, unit=UNIT,
            pm25=estimate.pm25_ug_m3, uncertainty=estimate.uncertainty_ug_m3, basis=basis,
            sensors=by_kind.get(SENSOR), reference=by_kind.get(REFERENCE),
            considerations=considerations, limitations=[c.message for c in considerations], audit=audit.steps)

    def _series(self, audit: AuditLog, lat: float, lon: float, start: Date, end: Date, resolution: str,
                radius_km: float, cutoff: float, min_hours: int
                ) -> tuple[list[SeriesPoint], SeriesSummary, list[Consideration]]:
        """Series, summary and considerations (the audit's closing 'versions' step is added by the caller)."""
        res = RESOLUTIONS[resolution]
        audit.log(RequestStep(lat=lat, lon=lon, start=start.isoformat(), end=end.isoformat(), resolution=resolution,
                              radius_km=radius_km, outlier_cutoff=cutoff,
                              min_hours_per_station=res.required_hours(min_hours), day_definition=DAY_DEFINITION))
        result = self._pipeline.run(audit, lat, lon, start, end, resolution, radius_km, cutoff, min_hours)

        series = [SeriesPoint(time=period, pm25=round(float(r["pm25"]), 2), uncertainty=round(float(r["uncertainty"]), 2),
                              basis=BASIS[r["kind"]], stations_used=int(r["stations"]))
                  for period, r in result.chosen.iterrows()]
        values = [p.pm25 for p in series]
        expected = res.expected_periods(start, end)
        audit.log(WeightedMeanStep(action="distance-weighted mean per period", weights=WEIGHT_FORMULA,
                                   periods=result.facts["periods"], periods_from_sensors=result.facts["sensor_periods"]))
        summary = SeriesSummary(periods_with_data=len(series), periods_expected=expected,
                                mean=round(sum(values) / len(values), 2), min=min(values), max=max(values))
        return series, summary, evaluate(self.rules, result.facts)

    def timeseries(self, lat: float, lon: float, start: Date, end: Date, resolution: str = "day",
                   radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> TimeseriesResponse:
        """Distance-weighted PM2.5 per day (or hour) for start..end (inclusive)."""
        audit = AuditLog()
        series, summary, considerations = self._series(audit, lat, lon, start, end, resolution, radius_km, cutoff,
                                                       min_hours)
        audit.log(VersionsStep(**self.versions))
        return TimeseriesResponse(location=Location(lat=lat, lon=lon), radius_km=radius_km, resolution=resolution,
                                  unit=UNIT, series=series, summary=summary, considerations=considerations,
                                  limitations=[c.message for c in considerations], audit=audit.steps)

    def compare(self, lat: float, lon: float, start: Date, end: Date, against: str = "who",
                radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> CompareResponse:
        """Compare the daily series for start..end with a set of reference levels."""
        audit = AuditLog()
        series, summary, considerations = self._series(audit, lat, lon, start, end, "day", radius_km, cutoff,
                                                       min_hours)
        comparisons, level_facts = compare_with_levels(series, self.guidelines[against], (end - start).days + 1)
        for facts in level_facts:
            considerations += evaluate(self.rules, facts, scope="level")
        audit.log(CompareStep(against=against,
                              levels=[c.model_dump(include={"id", "limit", "source", "verified"}) for c in comparisons]))
        audit.log(VersionsStep(**self.versions))
        return CompareResponse(location=Location(lat=lat, lon=lon), radius_km=radius_km, unit=UNIT, against=against,
                               comparisons=comparisons, summary=summary, considerations=considerations,
                               limitations=[c.message for c in considerations], audit=audit.steps)

    def weekday(self, lat: float, lon: float, start: Date, end: Date,
                radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> WeekdayResponse:
        """Weekday (Mon–Fri) vs. weekend (Sat–Sun) PM2.5 comparison over a date range."""
        audit = AuditLog()
        series, _, limitations = self._series(audit, lat, lon, start, end, "day", radius_km, cutoff, min_hours)
        wd_vals = [p.pm25 for p in series if Date.fromisoformat(p.time).weekday() < 5]
        we_vals = [p.pm25 for p in series if Date.fromisoformat(p.time).weekday() >= 5]

        def _grp(vals: list[float]) -> WeekdayGroup:
            return WeekdayGroup(n_days=len(vals),
                                mean=round(sum(vals) / len(vals), 2) if vals else 0.0,
                                min=round(min(vals), 2) if vals else 0.0,
                                max=round(max(vals), 2) if vals else 0.0)

        wd, we = _grp(wd_vals), _grp(we_vals)
        diff = round(we.mean - wd.mean, 2)
        audit.log("weekday vs weekend split", weekday_days=wd.n_days, weekend_days=we.n_days,
                  weekday_mean=wd.mean, weekend_mean=we.mean, difference=diff)
        audit.log("versions", **self.versions)
        return WeekdayResponse(location=Location(lat=lat, lon=lon), radius_km=radius_km, unit=UNIT,
                               weekday=wd, weekend=we, difference=diff,
                               limitations=limitations, audit=audit.steps)

    def trend(self, lat: float, lon: float, start: Date, end: Date,
              radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> TrendResponse:
        """Linear PM2.5 trend (slope µg/m³ per day) over a date range."""
        audit = AuditLog()
        series, summary, limitations = self._series(audit, lat, lon, start, end, "day", radius_km, cutoff, min_hours)
        xs = list(range(len(series)))
        ys = [p.pm25 for p in series]
        slope = _slope(xs, ys) if len(xs) >= 2 else 0.0
        direction = "stable" if abs(slope) < 0.05 else ("improving" if slope < 0 else "worsening")
        audit.log("linear trend", slope_ug_m3_per_day=round(slope, 4), direction=direction, n_points=len(xs))
        audit.log("versions", **self.versions)
        return TrendResponse(location=Location(lat=lat, lon=lon), radius_km=radius_km, unit=UNIT,
                             slope_ug_m3_per_day=round(slope, 4), direction=direction,
                             period_mean=summary.mean, n_days=len(xs),
                             limitations=limitations, audit=audit.steps)

    def events(self, lat: float, lon: float, start: Date, end: Date, threshold: float = 15.0,
               radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> EventsResponse:
        """Days with PM2.5 >= threshold in a date range."""
        audit = AuditLog()
        series, _, limitations = self._series(audit, lat, lon, start, end, "day", radius_km, cutoff, min_hours)
        event_days = [EventDay(date=p.time, pm25=p.pm25, uncertainty=p.uncertainty, basis=p.basis)
                      for p in series if p.pm25 >= threshold]
        share = round(len(event_days) / len(series), 3) if series else 0.0
        audit.log("events above threshold", threshold=threshold, n_events=len(event_days),
                  n_days_with_data=len(series), share_above=share)
        audit.log("versions", **self.versions)
        return EventsResponse(location=Location(lat=lat, lon=lon), radius_km=radius_km, unit=UNIT,
                              threshold=threshold, events=event_days, n_events=len(event_days),
                              n_days_with_data=len(series), share_above=share,
                              limitations=limitations, audit=audit.steps)

    def norms(self) -> GuidelinesNorms:
        """Frontend-ready norm values derived from the loaded guideline sets (fallback to canonical values)."""
        DEFAULTS = {"who": 5.0, "eu2030": 10.0, "euNow": 25.0, "who_daily": 15.0}
        mapping = {
            ("who", "annual"): "who",
            ("eu2030", "annual"): "eu2030",
            ("eu", "annual"): "euNow",
            ("who", "daily"): "who_daily",
        }
        result = dict(DEFAULTS)
        for set_name, levels in self.guidelines.items():
            for level in levels:
                key = mapping.get((set_name, level["type"]))
                if key:
                    result[key] = float(level["limit"])
        return GuidelinesNorms(**result)

    def coverage(self) -> CoverageResponse:
        return self._catalog.coverage(sorted(self.guidelines), self.versions)

    def stations(self, lat: float, lon: float, radius_km: float) -> StationsResponse:
        return self._catalog.stations(lat, lon, radius_km)
