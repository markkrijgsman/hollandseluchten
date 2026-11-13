"""PM2.5 estimate for a coordinate and date, with audit trail."""
import os
import subprocess
from dataclasses import dataclass
from datetime import date as Date, datetime, timezone
from functools import cached_property
from pathlib import Path

import pandas as pd

from .config import load_guidelines
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


def _log(audit: list[dict], step: str, **detail) -> None:
    audit.append({"step": len(audit) + 1, "action": step, **detail})


def _file_info(path: Path, date_range: tuple[str, str] | None = None) -> dict:
    st = path.stat()
    info = {"file": path.name, "size_bytes": st.st_size,
            "modified": datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")}
    if date_range:
        info["covers"] = {"from": date_range[0], "to": date_range[1]}
    return info


def _git_commit(directory: Path) -> str | None:
    try:
        out = subprocess.run(["git", "-C", str(directory), "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


class Pm25Service:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.reference = ReferenceRepository(settings.reference_measurements, settings.reference_metadata)
        self.sensors = SensorRepository(settings.sensor_parquet) if settings.sensor_parquet else None
        self.guidelines = load_guidelines()

    @cached_property
    def versions(self) -> dict:
        """Code and data this service runs on. Informational only (not used as a key anywhere)."""
        return {
            "analyse_together_commit": _git_commit(self.settings.analyse_together_dir),
            "reference_data": _file_info(self.settings.reference_measurements, self.reference.date_range),
            "sensor_data": (_file_info(self.settings.sensor_parquet, self.sensors.date_range)
                            if self.sensors else None),
        }

    def _nearby(self, df: pd.DataFrame, lat: float, lon: float, radius_km: float) -> pd.DataFrame:
        if df.empty:
            return df
        loc = df.groupby("station")[["lat", "lon"]].median()
        loc["distance_km"] = [haversine_km(lat, lon, la, lo) for la, lo in zip(loc["lat"], loc["lon"])]
        keep = loc[loc["distance_km"] <= radius_km]
        return df[df["station"].isin(keep.index)].merge(
            keep[["distance_km"]], left_on="station", right_index=True)

    def _prepare(self, lat: float, lon: float, start: Date, end: Date, radius_km: float,
                 cutoff: float, audit: list[dict]) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        """Select nearby stations for start..end and run the R functions once over all rows.

        Returns (station metadata, cleaned hourly rows with `sd`, R output incl. parameters).
        """
        period = start.isoformat() if start == end else f"{start} to {end}"
        ref = self._nearby(self.reference.hourly_range(start, end), lat, lon, radius_km)
        _log(audit, "select reference stations", source="Luchtmeetnet",
             stations=sorted(ref["station"].unique().tolist()), note="official stations; PM2.5 hourly values")
        frames = [ref.assign(parameter="pm25", kind="reference")]
        if self.sensors is not None:
            sens = self._nearby(self.sensors.hourly_range(start, end), lat, lon, radius_km)
            sens["station"] = SENSOR_PREFIX + sens["station"].astype(str)
            _log(audit, "select Hollandse Luchten sensors", source="Hollandse Luchten",
                 sensors=sorted(sens["station"].unique().tolist()), note="calibrated PM2.5 (pm25_kal), hourly mean")
            frames.append(sens.assign(parameter="pm25_kal", kind="sensor"))
        else:
            _log(audit, "select Hollandse Luchten sensors", skipped=True,
                 reason="no sensor data configured (HL_SENSOR_PARQUET)")
        frames = [f for f in frames if not f.empty]
        if not frames:
            raise NoDataError(f"No PM2.5 data within {radius_km} km for {period}", audit)
        data = pd.concat(frames, ignore_index=True)

        rows = [{"station": r.station, "parameter": r.parameter, "value": float(r.value), "date": r.hour}
                for r in data.itertuples()]
        r_out = run_r_analysis(rows, cutoff, self.settings.analyse_together_dir, self.settings.rscript)
        # functions and parameters are reported by R itself, so the audit shows what actually ran
        _log(audit, "R: Analyse-Together functions", functions=r_out["functions"],
             parameters=r_out["parameters"], hourly_values_in=len(rows), outliers_removed=r_out["removed_outliers"])
        clean = pd.DataFrame(r_out["rows"])
        if clean.empty:
            raise NoDataError("All values were removed as outliers", audit)
        meta = data.drop_duplicates("station").set_index("station")
        return meta, clean, r_out

    def compute(self, lat: float, lon: float, day: Date, radius_km: float = 5.0,
                cutoff: float = 100.0, min_hours: int = 18) -> dict:
        audit: list[dict] = []
        _log(audit, "request", lat=lat, lon=lon, date=day.isoformat(), radius_km=radius_km,
             outlier_cutoff=cutoff, min_hours_per_station=min_hours,
             day_definition="00:00-24:00 fixed UTC+1 (as in the Luchtmeetnet files)")

        meta, clean, r_out = self._prepare(lat, lon, day, day, radius_km, cutoff, audit)

        # daily mean per station
        per = clean.groupby("station").agg(hours=("value", "size"), mean=("value", "mean"), sd=("sd", "mean"))
        per = per.join(meta[["name", "kind", "distance_km"]])
        excluded = per[per["hours"] < min_hours]
        per = per[per["hours"] >= min_hours]
        _log(audit, "daily mean per station", stations_used=len(per),
             excluded_for_too_few_hours={s: int(h) for s, h in excluded["hours"].items()})
        if per.empty:
            raise NoDataError(f"No station has >= {min_hours} valid hours on {day}", audit)

        # distance-weighted mean (1/d^2) per source type
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
        _log(audit, "distance-weighted mean", weights=f"1/max(d, {MIN_DISTANCE_KM} km)^2", basis=basis,
             result=estimate["pm25_ug_m3"])

        pct = r_out["parameters"]["sensor_uncertainty_percent"]
        minimum = r_out["parameters"]["sensor_uncertainty_min_ug_m3"]
        limitations = [
            "Daily mean of hourly values; PM2.5 on a different day or hour can differ a lot.",
            "A weighted mean of nearby stations is an estimate, not a measurement at your coordinate.",
            f"Uncertainty of sensors is a fixed estimate ({pct:g}%, min {minimum:g} ug/m3) and is not reduced by averaging.",
        ]
        if basis == "reference_stations":
            limitations.append("No sensor data used: estimate is based on official stations only.")
        _log(audit, "versions", **self.versions)
        return {
            "date": day.isoformat(), "location": {"lat": lat, "lon": lon}, "radius_km": radius_km,
            "unit": "ug/m3", "pm25": estimate["pm25_ug_m3"], "uncertainty": estimate["uncertainty_ug_m3"],
            "basis": basis, "sensors": groups.get("sensor"), "reference": groups.get("reference"),
            "limitations": limitations, "audit": audit,
        }

    def timeseries(self, lat: float, lon: float, start: Date, end: Date, resolution: str = "day",
                   radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> dict:
        """Distance-weighted PM2.5 per day (or per hour) for start..end (inclusive).

        Same method as `compute`: R functions once over the whole range, then 1/max(d, 0.5 km)^2 weights
        per source type; sensors are preferred over reference stations in each period.
        """
        audit: list[dict] = []
        _log(audit, "request", lat=lat, lon=lon, start=start.isoformat(), end=end.isoformat(),
             resolution=resolution, radius_km=radius_km, outlier_cutoff=cutoff,
             min_hours_per_station=min_hours if resolution == "day" else 1,
             day_definition="00:00-24:00 fixed UTC+1 (as in the Luchtmeetnet files)")

        meta, clean, r_out = self._prepare(lat, lon, start, end, radius_km, cutoff, audit)

        width = 10 if resolution == "day" else 13
        clean = clean.assign(period=clean["date"].str[:width])
        per = clean.groupby(["period", "station"]).agg(hours=("value", "size"), mean=("value", "mean"), sd=("sd", "mean"))
        per = per.join(meta[["kind", "distance_km"]], on="station")
        needed = min_hours if resolution == "day" else 1
        n_before = len(per)
        per = per[per["hours"] >= needed]
        _log(audit, f"{resolution} mean per station", station_periods_used=len(per),
             station_periods_excluded_for_too_few_hours=n_before - len(per))
        if per.empty:
            raise NoDataError(f"No station has enough valid hours between {start} and {end}", audit)

        per["w"] = 1.0 / per["distance_km"].clip(lower=MIN_DISTANCE_KM) ** 2
        per["wm"] = per["mean"] * per["w"]
        per["wu"] = per["sd"] * per["w"]  # weighted mean of uncertainties (errors fully correlated, conservative)
        agg = per.groupby(["period", "kind"]).agg(w=("w", "sum"), wm=("wm", "sum"), wu=("wu", "sum"),
                                                   stations=("w", "size")).reset_index()
        agg["pm25"] = agg["wm"] / agg["w"]
        agg["uncertainty"] = agg["wu"] / agg["w"]
        series, sensor_periods = [], 0
        for period, g in agg.groupby("period"):
            kinds = g.set_index("kind")
            kind = "sensor" if "sensor" in kinds.index else "reference"
            row = kinds.loc[kind]
            sensor_periods += kind == "sensor"
            series.append({"time": period, "pm25": round(float(row["pm25"]), 2),
                           "uncertainty": round(float(row["uncertainty"]), 2),
                           "basis": "sensors" if kind == "sensor" else "reference_stations",
                           "stations_used": int(row["stations"])})
        values = [p["pm25"] for p in series]
        expected = ((end - start).days + 1) * (1 if resolution == "day" else 24)
        summary = {"periods_with_data": len(series), "periods_expected": expected,
                   "mean": round(sum(values) / len(values), 2), "min": min(values), "max": max(values)}
        _log(audit, "distance-weighted mean per period", weights=f"1/max(d, {MIN_DISTANCE_KM} km)^2",
             periods=len(series), periods_from_sensors=int(sensor_periods))

        pct = r_out["parameters"]["sensor_uncertainty_percent"]
        minimum = r_out["parameters"]["sensor_uncertainty_min_ug_m3"]
        limitations = [
            "A weighted mean of nearby stations is an estimate, not a measurement at your coordinate.",
            f"Uncertainty of sensors is a fixed estimate ({pct:g}%, min {minimum:g} ug/m3) and is not reduced by averaging.",
            "The summary mean is the plain mean of the periods that have data; periods without data are skipped.",
        ]
        if sensor_periods < len(series):
            limitations.append("Periods without sensor data use official stations only; the basis can change over the series.")
        if summary["periods_with_data"] < expected:
            limitations.append(f"{expected - summary['periods_with_data']} of {expected} periods have no usable data.")
        _log(audit, "versions", **self.versions)
        return {
            "location": {"lat": lat, "lon": lon}, "radius_km": radius_km, "resolution": resolution,
            "unit": "ug/m3", "series": series, "summary": summary, "limitations": limitations, "audit": audit,
        }

    def compare(self, lat: float, lon: float, start: Date, end: Date, against: str = "who",
                radius_km: float = 5.0, cutoff: float = 100.0, min_hours: int = 18) -> dict:
        """Compare the daily series for start..end with WHO or EU reference levels."""
        ts = self.timeseries(lat, lon, start, end, "day", radius_km, cutoff, min_hours)
        series, audit = ts["series"], ts["audit"]
        days = (end - start).days + 1
        comparisons, limitations = [], list(ts["limitations"])
        for g in self.guidelines[against]:
            limit = g["limit"]
            if g["type"] == "daily":
                above = [p for p in series if p["pm25"] > limit]
                comparisons.append({
                    **g, "days_with_data": len(series), "days_above": len(above),
                    "share_above": round(len(above) / len(series), 3),
                    # uncertainty range: sure vs possible exceedances
                    "days_above_even_at_lower_bound": sum(p["pm25"] - p["uncertainty"] > limit for p in series),
                    "days_above_at_upper_bound": sum(p["pm25"] + p["uncertainty"] > limit for p in series),
                })
            else:
                mean = sum(p["pm25"] for p in series) / len(series)
                unc = sum(p["uncertainty"] for p in series) / len(series)
                comparisons.append({**g, "period_mean": round(mean, 2), "uncertainty": round(unc, 2),
                                    "exceeded": mean > limit, "uncertain": abs(mean - limit) <= unc})
                if days < 300:
                    limitations.append(
                        f"'{g['name']}' is defined for a full year; your period is {days} days, so this is only indicative.")
        _log(audit, "compare with reference levels", against=against,
             levels=[{k: c[k] for k in ("id", "limit", "source", "verified")} for c in comparisons])
        return {"location": ts["location"], "radius_km": radius_km, "unit": "ug/m3", "against": against,
                "comparisons": comparisons, "summary": ts["summary"], "limitations": limitations, "audit": audit}

    def coverage(self) -> dict:
        ref = self.reference.pm25_stations()
        out = {
            "unit": "ug/m3", "day_definition": "00:00-24:00 fixed UTC+1",
            "reference_stations": {"from": self.reference.date_range[0], "to": self.reference.date_range[1],
                                   "stations": len(ref)},
            "sensors": None, "guideline_sets": sorted(self.guidelines),
            "versions": self.versions,
            "limitations": ["The ranges are the union over all stations. Individual stations can stop earlier: "
                            "use /stations for the data period near a specific location."],
        }
        if self.sensors:
            kits = self.sensors.kit_stations()
            out["sensors"] = {"from": kits["data_from"].min(), "to": kits["data_to"].max(), "stations": len(kits)}
        return out

    def stations(self, lat: float, lon: float, radius_km: float) -> dict:
        """Stations within radius_km, nearest first, with the period they have PM2.5 data."""
        frames = [self.reference.pm25_stations().assign(kind="reference")]
        if self.sensors:
            frames.append(self.sensors.kit_stations().assign(kind="sensor"))
        df = pd.concat(frames, ignore_index=True)
        df["distance_km"] = [haversine_km(lat, lon, la, lo) for la, lo in zip(df["lat"], df["lon"])]
        df = df[df["distance_km"] <= radius_km].sort_values("distance_km")
        keep = ["station", "name", "kind", "distance_km", "lat", "lon", "station_type", "area_type", "data_from", "data_to"]
        rows = df.reindex(columns=keep).astype(object).where(df.reindex(columns=keep).notna(), None)
        out = []
        for r in rows.to_dict("records"):
            r["id"] = r.pop("station")
            r["distance_km"] = round(float(r["distance_km"]), 2)
            out.append(r)
        return {"location": {"lat": lat, "lon": lon}, "radius_km": radius_km, "count": len(out), "stations": out,
                "limitations": ["data_from/data_to give the first and last day with PM2.5 data; there can be gaps in between."]}
