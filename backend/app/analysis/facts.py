"""Facts about one run: plain numbers and flags that considerations (config/considerations.toml) are written against.

The pipeline records facts; it never writes prose. A rule can only refer to a fact listed in FACTS, and this is checked
when the rules are loaded.
"""
from __future__ import annotations

from datetime import date as Date

import pandas as pd

from .constants import BASIS, SENSOR
from .periods import Resolution

FACTS: dict[str, str] = {
    # whole run
    "resolution": "'day' or 'hour'",
    "single_period": "the request covers exactly one period",
    "basis": "'sensors', 'reference_stations' or 'mixed' (differs per period)",
    "periods": "periods with a result",
    "periods_expected": "periods in the requested range",
    "periods_without_data": "expected periods without a result",
    "sensors_configured": "a sensor data file is configured",
    "sensor_periods": "periods whose result comes from sensors",
    "periods_on_reference": "periods whose result comes from official stations",
    "hourly_values_in": "hourly values passed to the R functions",
    "outliers_removed": "hourly values the R outlier cut-off removed",
    "outlier_share": "outliers_removed / hourly_values_in",
    "outlier_cutoff": "cut-off value used (ug/m3)",
    "sensor_uncertainty_percent": "sensor uncertainty reported by R (% of the value)",
    "sensor_uncertainty_min": "minimum sensor uncertainty reported by R (ug/m3)",
    "required_hours": "valid hours a station needs per period",
    "station_periods_used": "station-periods with enough valid hours",
    "stations_excluded": "station-periods left out for too few valid hours",
    "traffic_weight_share": "largest weight share of traffic stations in any period (only official stations have a type)",
    "industry_weight_share": "largest weight share of industrial stations in any period",
    "nearest_km": "distance to the nearest station used in the result",
    "min_stations": "fewest stations behind any period's result",
    "max_share": "largest weight share of one station in the result",
    "uncertainty_ratio": "mean of uncertainty / value over the periods",
    # per geocoded place
    "place_query": "what the user asked for",
    "place_candidates": "number of places the geocoder returned",
    "place_chosen": "the place that was used (the geocoder's first match)",
    "place_alternatives": "the other matches, separated by '; '",
    # per reference level (compare)
    "level_name": "name of the reference level",
    "level_type": "'daily' or 'annual'",
    "level_limit": "the level (ug/m3)",
    "level_verified": "the level was checked against its source",
    "period_days": "days in the requested range",
    "days_with_data": "days with a result",
    "ambiguous_days": "days whose uncertainty range contains the level",
    "period_mean": "mean over the period (ug/m3)",
    "mean_uncertainty": "mean uncertainty over the period (ug/m3)",
    "level_uncertain": "the period mean is within its uncertainty of the level",
}


def load_facts(rows_in: int, removed: int, r_parameters: dict, sensors_configured: bool) -> dict:
    """Facts of the loading stage (what the R functions did). The audit step is built from the same dict."""
    return {
        "sensors_configured": sensors_configured,
        "hourly_values_in": rows_in, "outliers_removed": removed,
        "outlier_share": removed / rows_in if rows_in else 0.0,
        "outlier_cutoff": r_parameters["outlier_cutoff"],
        "sensor_uncertainty_percent": r_parameters["sensor_uncertainty_percent"],
        "sensor_uncertainty_min": r_parameters["sensor_uncertainty_min_ug_m3"],
    }


def means_facts(per: pd.DataFrame, excluded: pd.DataFrame, required_hours: int) -> dict:
    """Facts of the per-station stage. `per` holds the stations that were kept."""
    return {"required_hours": required_hours, "station_periods_used": len(per), "stations_excluded": len(excluded)}


def result_facts(per: pd.DataFrame, chosen: pd.DataFrame, res: Resolution, start: Date, end: Date) -> dict:
    """Facts of the result. `per` has weights; `chosen` has one row per period (kind, stations, pm25, uncertainty)."""
    kinds = set(chosen["kind"])
    expected = res.expected_periods(start, end)
    sensor_periods = int((chosen["kind"] == SENSOR).sum())
    used = per.reset_index().merge(chosen["kind"].rename("chosen").reset_index(), on="period")
    used = used[used["kind"] == used["chosen"]]
    positive = chosen[chosen["pm25"] > 0]
    ratio = float((positive["uncertainty"] / positive["pm25"]).mean()) if len(positive) else None

    def worst_share(station_type: str) -> float:  # largest weight share of this type in any period
        return float(used["share"].where(used["station_type"] == station_type, 0.0)
                     .groupby(used["period"]).sum().max())

    return {
        "resolution": res.name,
        "single_period": start == end,
        "basis": BASIS[next(iter(kinds))] if len(kinds) == 1 else "mixed",
        "periods": len(chosen), "periods_expected": expected, "periods_without_data": expected - len(chosen),
        "sensor_periods": sensor_periods, "periods_on_reference": len(chosen) - sensor_periods,
        "nearest_km": float(used["distance_km"].min()),
        "min_stations": int(chosen["stations"].min()),
        "max_share": float(used["share"].max()),
        "traffic_weight_share": worst_share("verkeer"),
        "industry_weight_share": worst_share("industrie"),
        "uncertainty_ratio": ratio,
    }
