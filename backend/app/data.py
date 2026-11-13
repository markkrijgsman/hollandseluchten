"""Hourly PM2.5 data access. Days are fixed UTC+1, matching the Luchtmeetnet files."""
from datetime import date as Date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

FIXED_TZ_OFFSET = pd.Timedelta(hours=1)


def _day_bounds(day: Date) -> tuple[str, str]:
    return f"{day.isoformat()}T00", f"{(day + timedelta(days=1)).isoformat()}T00"


class ReferenceRepository:
    """Official Luchtmeetnet stations (hourly PM2.5)."""

    def __init__(self, measurements: Path, metadata: Path):
        self.measurements = measurements
        self.stations = pd.read_csv(metadata)
        self._range: tuple[str, str] | None = None

    @property
    def date_range(self) -> tuple[str, str]:
        if self._range is None:
            col = pq.read_table(self.measurements, columns=["begindatumtijd"]).column(0).to_pandas()
            self._range = (col.min()[:10], col.max()[:10])
        return self._range

    def hourly(self, day: Date) -> pd.DataFrame:
        lo, hi = _day_bounds(day)
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


class SensorRepository:
    """Hollandse Luchten sensor kits (hourly calibrated PM2.5)."""

    def __init__(self, path: Path):
        self.path = path
        self._range: tuple[str, str] | None = None

    @property
    def date_range(self) -> tuple[str, str]:
        if self._range is None:
            col = pq.read_table(self.path, columns=["timestamp_from"]).column(0).to_pandas()
            self._range = ((col.min() + FIXED_TZ_OFFSET).date().isoformat(),
                           (col.max() + FIXED_TZ_OFFSET).date().isoformat())
        return self._range

    def hourly(self, day: Date) -> pd.DataFrame:
        start = pd.Timestamp(day.isoformat(), tz="UTC") - FIXED_TZ_OFFSET
        end = start + pd.Timedelta(days=1)
        df = pq.read_table(
            self.path, columns=["kit_id", "timestamp_from", "pm25_kal", "latitude", "longitude"],
            filters=[("timestamp_from", ">=", start.to_pydatetime()), ("timestamp_from", "<", end.to_pydatetime())],
        ).to_pandas()
        df = df.dropna(subset=["pm25_kal", "latitude", "longitude"])
        if df.empty:
            return pd.DataFrame(columns=["station", "hour", "value", "lat", "lon", "name"])
        ts = pd.to_datetime(df["timestamp_from"], utc=True) + FIXED_TZ_OFFSET
        df["hour"] = ts.dt.strftime("%Y-%m-%dT%H")
        out = df.groupby(["kit_id", "hour"], as_index=False).agg(
            value=("pm25_kal", "mean"), lat=("latitude", "median"), lon=("longitude", "median"))
        out = out.rename(columns={"kit_id": "station"})
        out["name"] = out["station"]
        return out
