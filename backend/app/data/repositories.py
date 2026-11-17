"""Hourly PM2.5 data access. Days are fixed UTC+1, matching the Luchtmeetnet files."""
from __future__ import annotations

from datetime import date as Date
from datetime import timedelta
from pathlib import Path
from threading import Lock

import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from ..analysis.geo import NL_LAT, NL_LON

FIXED_TZ_OFFSET = pd.Timedelta(hours=1)


def _day_bounds(start: Date, end: Date | None = None) -> tuple[str, str]:
    """[start 00:00, end+1 00:00) as ISO hour strings; end defaults to start (one day)."""
    return f"{start.isoformat()}T00", f"{((end or start) + timedelta(days=1)).isoformat()}T00"


class ReferenceRepository:
    """Official Luchtmeetnet stations (hourly PM2.5)."""

    def __init__(self, measurements: Path, metadata: Path):
        self.measurements = measurements
        self.stations = pd.read_csv(metadata)
        self._stations: pd.DataFrame | None = None
        self._lock = Lock()

    def pm25_stations(self) -> pd.DataFrame:
        """Stations with PM2.5 data: id, name, lat, lon, types, first/last hour (date) and number of hourly values."""
        if self._stations is None:
            with self._lock:
                if self._stations is None:
                    t = pq.read_table(self.measurements, columns=["meetlocatie_id", "begindatumtijd", "waarde"],
                                      filters=[("component", "==", "PM2.5")]).to_pandas().dropna(subset=["waarde"])
                    g = t.groupby("meetlocatie_id", observed=True)["begindatumtijd"].agg(
                        data_from="min", data_to="max", hourly_values="size")
                    g["data_from"], g["data_to"] = g["data_from"].str[:10], g["data_to"].str[:10]
                    meta = self.stations.rename(columns={
                        "meetlocatie_id": "station", "meetlocatie_naam": "name", "breedtegraad": "lat",
                        "lengtegraad": "lon", "stationstype": "station_type", "gebiedstype": "area_type"})
                    self._stations = g.rename_axis("station").reset_index().merge(
                        meta[["station", "name", "lat", "lon", "station_type", "area_type"]], on="station", how="inner")
        return self._stations

    @property
    def date_range(self) -> tuple[str, str]:
        st = self.pm25_stations()
        return st["data_from"].min(), st["data_to"].max()

    def hourly(self, day: Date) -> pd.DataFrame:
        return self.hourly_range(day, day)

    def hourly_range(self, start: Date, end: Date) -> pd.DataFrame:
        lo, hi = _day_bounds(start, end)
        table = pq.read_table(
            self.measurements,
            columns=["meetlocatie_id", "begindatumtijd", "waarde"],
            filters=[("component", "==", "PM2.5"), ("begindatumtijd", ">=", lo), ("begindatumtijd", "<", hi)],
        )
        df = table.to_pandas().rename(columns={"meetlocatie_id": "station", "waarde": "value", "begindatumtijd": "hour"})
        df["hour"] = df["hour"].str[:13]
        df = df.dropna(subset=["value"])
        meta = self.stations.rename(columns={
            "meetlocatie_id": "station", "meetlocatie_naam": "name", "breedtegraad": "lat",
            "lengtegraad": "lon"})[["station", "name", "lat", "lon", "stationstype", "gebiedstype"]]
        return df.merge(meta, on="station", how="inner")


def _with_valid_position(df: pd.DataFrame) -> pd.DataFrame:
    """Rows with a calibrated value and a GPS position inside the Netherlands (the file has 0,0 and foreign fixes)."""
    df = df.dropna(subset=["pm25_kal", "latitude", "longitude"])
    return df[df["latitude"].between(*NL_LAT) & df["longitude"].between(*NL_LON)]


class SensorRepository:
    """Hollandse Luchten sensor kits (hourly calibrated PM2.5)."""

    def __init__(self, path: Path):
        self.path = path
        self._range: tuple[str, str] | None = None
        self._stations: pd.DataFrame | None = None
        self._lock = Lock()

    def kit_stations(self) -> pd.DataFrame:
        """Kits with calibrated PM2.5: id, name, lat, lon, first/last day (UTC+1) and number of hourly-ish values."""
        if self._stations is None:
            with self._lock:
                if self._stations is None:
                    cache = self.path.with_name(f".{self.path.name}.{self.path.stat().st_size}.kits.parquet")
                    if cache.exists():
                        self._stations = pd.read_parquet(cache)
                    else:
                        t = _with_valid_position(pq.read_table(
                            self.path, columns=["kit_id", "timestamp_from", "pm25_kal", "latitude", "longitude"]).to_pandas())
                        g = t.groupby("kit_id", observed=True).agg(
                            ts_min=("timestamp_from", "min"),
                            ts_max=("timestamp_from", "max"),
                            lat=("latitude", "median"),
                            lon=("longitude", "median"),
                        )
                        g["data_from"] = (pd.to_datetime(g["ts_min"], utc=True) + FIXED_TZ_OFFSET).dt.strftime("%Y-%m-%d")
                        g["data_to"] = (pd.to_datetime(g["ts_max"], utc=True) + FIXED_TZ_OFFSET).dt.strftime("%Y-%m-%d")
                        g = g.drop(columns=["ts_min", "ts_max"])
                        self._stations = g.rename_axis("station").reset_index().assign(name=lambda d: d["station"])
                        try:
                            self._stations.to_parquet(cache, index=False)
                        except OSError:
                            pass
        return self._stations

    @property
    def date_range(self) -> tuple[str, str]:
        if self._range is None:
            with self._lock:
                if self._range is None:
                    col = pq.read_table(self.path, columns=["timestamp_from"]).column(0)
                    mm = pc.min_max(col).as_py()
                    lo = (pd.Timestamp(mm["min"]) + FIXED_TZ_OFFSET).date().isoformat()
                    hi = (pd.Timestamp(mm["max"]) + FIXED_TZ_OFFSET).date().isoformat()
                    self._range = (lo, hi)
        return self._range

    def hourly(self, day: Date) -> pd.DataFrame:
        return self.hourly_range(day, day)

    def hourly_range(self, first: Date, last: Date) -> pd.DataFrame:
        # the sensor file stores naive UTC timestamps, so the filter bounds are naive too
        start = pd.Timestamp(first.isoformat()) - FIXED_TZ_OFFSET
        end = pd.Timestamp(last.isoformat()) - FIXED_TZ_OFFSET + pd.Timedelta(days=1)
        df = pq.read_table(
            self.path, columns=["kit_id", "timestamp_from", "pm25_kal", "latitude", "longitude"],
            filters=[("timestamp_from", ">=", start.to_pydatetime()), ("timestamp_from", "<", end.to_pydatetime())],
        ).to_pandas()
        df = _with_valid_position(df)
        if df.empty:
            return pd.DataFrame(columns=["station", "hour", "value", "lat", "lon", "name"])
        ts = pd.to_datetime(df["timestamp_from"], utc=True) + FIXED_TZ_OFFSET
        df["hour"] = ts.dt.strftime("%Y-%m-%dT%H")
        out = df.groupby(["kit_id", "hour"], as_index=False).agg(
            value=("pm25_kal", "mean"), lat=("latitude", "median"), lon=("longitude", "median"))
        out = out.rename(columns={"kit_id": "station"})
        out["name"] = out["station"]
        return out
