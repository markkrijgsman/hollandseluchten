"""PM2.5 estimate for a coordinate and date, with audit trail."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date as Date
from pathlib import Path

import pandas as pd

from .data import ReferenceRepository, SensorRepository
from .geo import haversine_km
from .rbridge import run_r_analysis

REPO_ROOT = Path(__file__).resolve().parent.parent
MIN_DISTANCE_KM = 0.5  # distance floor so a station at ~0 km does not get an infinite weight
SENSOR_PREFIX = "HL_"  # keeps kit ids from matching the reference-station pattern "^NL.[0-9]." in R


class NoDataError(Exception):
    def __init__(self, message: str, audit: list[dict]):
        super().__init__(message)
        self.audit = audit


@dataclass
class Settings:
    reference_measurements: Path
    reference_metadata: Path
    analyse_together_dir: Path
    sensor_parquet: Path | None = None
    rscript: str = "Rscript"

    @classmethod
    def from_env(cls) -> "Settings":
        data = Path(os.environ.get("HL_DATA_DIR", REPO_ROOT.parent.parent / "HackathonHollandseLuchten" / "data"))
        sensors = os.environ.get("HL_SENSOR_PARQUET")
        return cls(
            reference_measurements=data / "reference_measurements.parquet",
            reference_metadata=data / "reference_station_metadata.csv",
            analyse_together_dir=Path(os.environ.get("HL_ANALYSE_TOGETHER_DIR", REPO_ROOT.parent.parent / "Analyse-Together")),
            sensor_parquet=Path(sensors) if sensors else None,
            rscript=os.environ.get("HL_RSCRIPT", "Rscript"),
        )


class Pm25Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reference = ReferenceRepository(settings.reference_measurements, settings.reference_metadata)
        self.sensors = SensorRepository(settings.sensor_parquet) if settings.sensor_parquet else None

    def _nearby(self, df: pd.DataFrame, lat: float, lon: float, radius_km: float) -> pd.DataFrame:
        if df.empty:
            return df
        loc = df.groupby("station")[["lat", "lon"]].median()
        loc["distance_km"] = [haversine_km(lat, lon, la, lo) for la, lo in zip(loc["lat"], loc["lon"])]
        keep = loc[loc["distance_km"] <= radius_km]
        return df[df["station"].isin(keep.index)].merge(
            keep[["distance_km"]], left_on="station", right_index=True)

    def compute(self, lat: float, lon: float, day: Date, radius_km: float = 5.0,
                cutoff: float = 100.0, min_hours: int = 18) -> dict:
        audit: list[dict] = []

        def log(step: str, **detail):
            audit.append({"step": len(audit) + 1, "action": step, **detail})

        log("request", lat=lat, lon=lon, date=day.isoformat(), radius_km=radius_km,
            outlier_cutoff=cutoff, min_hours_per_station=min_hours,
            day_definition="00:00-24:00 fixed UTC+1 (as in the Luchtmeetnet files)")

        # 1. load + select stations within radius
        ref = self._nearby(self.reference.hourly(day), lat, lon, radius_km)
        log("select reference stations", source="Luchtmeetnet", stations=sorted(ref["station"].unique().tolist()),
            note="official stations; PM2.5 hourly values")
        frames = [ref.assign(parameter="pm25", kind="reference")]
        if self.sensors is not None:
            sens = self._nearby(self.sensors.hourly(day), lat, lon, radius_km)
            sens["station"] = SENSOR_PREFIX + sens["station"].astype(str)
            log("select Hollandse Luchten sensors", source="Hollandse Luchten", sensors=sorted(sens["station"].unique().tolist()),
                note="calibrated PM2.5 (pm25_kal), hourly mean")
            frames.append(sens.assign(parameter="pm25_kal", kind="sensor"))
        else:
            log("select Hollandse Luchten sensors", skipped=True, reason="no sensor data configured (HL_SENSOR_PARQUET)")
        data = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else pd.DataFrame()
        if data.empty:
            raise NoDataError(f"No PM2.5 data within {radius_km} km on {day}", audit)

        # 2. validated R functions: calibration flag, outlier cut-off, uncertainty
        rows = [{"station": r.station, "parameter": r.parameter, "value": float(r.value), "date": r.hour}
                for r in data.itertuples()]
        r_out = run_r_analysis(rows, cutoff, self.settings.analyse_together_dir, self.settings.rscript)
        log("R: Analyse-Together functions", functions=r_out["functions"], hourly_values_in=len(rows),
            outliers_removed=r_out["removed_outliers"],
            uncertainty="sensors: 20% of value, min 5.3 ug/m3; reference stations: 0")
        clean = pd.DataFrame(r_out["rows"])
        if clean.empty:
            raise NoDataError("All values were removed as outliers", audit)

        # 3. daily mean per station
        meta = data.drop_duplicates("station").set_index("station")
        per = clean.groupby("station").agg(hours=("value", "size"), mean=("value", "mean"), sd=("sd", "mean"))
        per = per.join(meta[["name", "kind", "distance_km"]])
        excluded = per[per["hours"] < min_hours]
        per = per[per["hours"] >= min_hours]
        log("daily mean per station", stations_used=len(per),
            excluded_for_too_few_hours={s: int(h) for s, h in excluded["hours"].items()})
        if per.empty:
            raise NoDataError(f"No station has >= {min_hours} valid hours on {day}", audit)

        # 4. distance-weighted mean (1/d^2) per source type
        per["weight"] = 1.0 / per["distance_km"].clip(lower=MIN_DISTANCE_KM) ** 2

        def idw(group: pd.DataFrame) -> dict:
            w = group["weight"] / group["weight"].sum()
            return {
                "pm25_ug_m3": round(float((group["mean"] * w).sum()), 2),
                # errors are treated as fully correlated: weighted mean of uncertainties (conservative)
                "uncertainty_ug_m3": round(float((group["sd"] * w).sum()), 2),
                "stations": [
                    {"id": s.removeprefix(SENSOR_PREFIX), "name": g["name"], "distance_km": round(float(g["distance_km"]), 2),
                     "weight": round(float(w[s]), 3), "daily_mean": round(float(g["mean"]), 2),
                     "uncertainty": round(float(g["sd"]), 2), "valid_hours": int(g["hours"])}
                    for s, g in group.sort_values("distance_km").iterrows()],
            }

        groups = {k: idw(g) for k, g in per.groupby("kind")}
        basis = "sensors" if "sensor" in groups else "reference_stations"
        estimate = groups["sensor" if basis == "sensors" else "reference"]
        log("distance-weighted mean", weights="1/max(d, 0.5 km)^2", basis=basis,
            result=estimate["pm25_ug_m3"])

        limitations = [
            "Daily mean of hourly values; PM2.5 on a different day or hour can differ a lot.",
            "A weighted mean of nearby stations is an estimate, not a measurement at your coordinate.",
            "Uncertainty of sensors is a fixed estimate (20%, min 5.3 ug/m3) and is not reduced by averaging.",
        ]
        if basis == "reference_stations":
            limitations.append("No sensor data used: estimate is based on official stations only.")
        return {
            "date": day.isoformat(), "location": {"lat": lat, "lon": lon}, "radius_km": radius_km,
            "unit": "ug/m3", "pm25": estimate["pm25_ug_m3"], "uncertainty": estimate["uncertainty_ug_m3"],
            "basis": basis, "sensors": groups.get("sensor"), "reference": groups.get("reference"),
            "limitations": limitations, "audit": audit,
        }
