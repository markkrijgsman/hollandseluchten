"""Facade over the analyses. Each method builds one response; the work is done by the modules it composes."""
from datetime import date as Date
from functools import cached_property

from ..data.repositories import ReferenceRepository, SensorRepository
from ..settings import Settings
from . import limitations as notes
from . import weighting
from .audit import AuditLog
from .catalog import Catalog
from .compare import compare_with_levels
from .constants import BASIS, DAY_DEFINITION, REFERENCE, SENSOR, UNIT, WEIGHT_FORMULA
from .guidelines import load_guidelines
from .observations import ObservationLoader
from .periods import RESOLUTIONS
from .pipeline import Pipeline
from .versions import collect_versions


class Pm25Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reference = ReferenceRepository(settings.reference_measurements, settings.reference_metadata)
        self.sensors = SensorRepository(settings.sensor_parquet) if settings.sensor_parquet else None
        self.guidelines = load_guidelines()
        self._pipeline = Pipeline(ObservationLoader(settings, self.reference, self.sensors))
        self._catalog = Catalog(self.reference, self.sensors)

    @cached_property
    def versions(self) -> dict:
        return collect_versions(self.settings, self.reference, self.sensors)

    def compute(self, lat: float, lon: float, day: Date, radius_km: float = 5.0,
                cutoff: float = 100.0, min_hours: int = 18) -> dict:
        """Distance-weighted daily mean at a point, with the per-station breakdown."""
        audit = AuditLog()
        audit.log("request", lat=lat, lon=lon, date=day.isoformat(), radius_km=radius_km, outlier_cutoff=cutoff,
                  min_hours_per_station=min_hours, day_definition=DAY_DEFINITION)
        result = self._pipeline.run(audit, lat, lon, day, day, "day", radius_km, cutoff, min_hours)

        period = day.isoformat()
        by_kind = {}
        for kind in (SENSOR, REFERENCE):
            if (period, kind) in result.estimates.index:
                est = result.estimates.loc[(period, kind)]
                by_kind[kind] = {
                    "pm25_ug_m3": round(float(est["pm25"]), 2), "uncertainty_ug_m3": round(float(est["uncertainty"]), 2),
                    "stations": weighting.station_breakdown(result.per[result.per["kind"] == kind]),
                }
        chosen_kind = result.chosen.loc[period, "kind"]
        basis, estimate = BASIS[chosen_kind], by_kind[chosen_kind]
        audit.log("distance-weighted mean", weights=WEIGHT_FORMULA, basis=basis, result=estimate["pm25_ug_m3"])
        audit.log("versions", **self.versions)
        return {
            "date": period, "location": {"lat": lat, "lon": lon}, "radius_km": radius_km, "unit": UNIT,
            "pm25": estimate["pm25_ug_m3"], "uncertainty": estimate["uncertainty_ug_m3"], "basis": basis,
            "sensors": by_kind.get(SENSOR), "reference": by_kind.get(REFERENCE),
            "limitations": notes.daily_limitations(result.r_parameters, basis), "audit": audit.steps,
        }

    def _series(self, audit: AuditLog, lat: float, lon: float, start: Date, end: Date, resolution: str,
                radius_km: float, cutoff: float, min_hours: int) -> dict:
        """The series, its summary and limitations (everything except the audit's closing 'versions' step)."""
        res = RESOLUTIONS[resolution]
        audit.log("request", lat=lat, lon=lon, start=start.isoformat(), end=end.isoformat(), resolution=resolution,
                  radius_km=radius_km, outlier_cutoff=cutoff, min_hours_per_station=res.required_hours(min_hours),
                  day_definition=DAY_DEFINITION)
        result = self._pipeline.run(audit, lat, lon, start, end, resolution, radius_km, cutoff, min_hours)

        series = [{"time": period, "pm25": round(float(r["pm25"]), 2), "uncertainty": round(float(r["uncertainty"]), 2),
                   "basis": BASIS[r["kind"]], "stations_used": int(r["stations"])}
                  for period, r in result.chosen.iterrows()]
        sensor_periods = int((result.chosen["kind"] == SENSOR).sum())
        values = [p["pm25"] for p in series]
        expected = res.expected_periods(start, end)
        audit.log("distance-weighted mean per period", weights=WEIGHT_FORMULA, periods=len(series),
                  periods_from_sensors=sensor_periods)
        return {
            "location": {"lat": lat, "lon": lon}, "radius_km": radius_km, "resolution": resolution, "unit": UNIT,
            "series": series,
            "summary": {"periods_with_data": len(series), "periods_expected": expected,
                        "mean": round(sum(values) / len(values), 2), "min": min(values), "max": max(values)},
            "limitations": notes.series_limitations(result.r_parameters, sensor_periods, len(series), expected),
        }

    def timeseries(self, lat: float, lon: float, start: Date, end: Date, resolution: str = "day",
                   radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> dict:
        """Distance-weighted PM2.5 per day (or hour) for start..end (inclusive)."""
        audit = AuditLog()
        body = self._series(audit, lat, lon, start, end, resolution, radius_km, cutoff, min_hours)
        audit.log("versions", **self.versions)
        return {**body, "audit": audit.steps}

    def compare(self, lat: float, lon: float, start: Date, end: Date, against: str = "who",
                radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> dict:
        """Compare the daily series for start..end with a set of reference levels."""
        audit = AuditLog()
        ts = self._series(audit, lat, lon, start, end, "day", radius_km, cutoff, min_hours)
        comparisons, extra = compare_with_levels(ts["series"], self.guidelines[against], (end - start).days + 1)
        audit.log("compare with reference levels", against=against,
                  levels=[{k: c[k] for k in ("id", "limit", "source", "verified")} for c in comparisons])
        audit.log("versions", **self.versions)
        return {"location": ts["location"], "radius_km": radius_km, "unit": UNIT, "against": against,
                "comparisons": comparisons, "summary": ts["summary"],
                "limitations": [*ts["limitations"], *extra], "audit": audit.steps}

    def coverage(self) -> dict:
        return self._catalog.coverage(sorted(self.guidelines), self.versions)

    def stations(self, lat: float, lon: float, radius_km: float) -> dict:
        return self._catalog.stations(lat, lon, radius_km)
