"""Constants and writers for the synthetic data the tests run on (no dependency on the hackathon repo)."""
import os
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

BACKEND = Path(__file__).resolve().parent.parent
AT_DIR = Path(os.environ.get("HL_ANALYSE_TOGETHER_DIR", BACKEND.parent.parent / "Analyse-Together"))
REAL_DATA = Path(os.environ.get("HL_DATA_DIR", BACKEND.parent.parent / "HackathonHollandseLuchten" / "data"))

LAT, LON = 52.3676, 4.9041
DAY = date(2025, 5, 1)
DAY_START_UTC = datetime(2025, 4, 30, 23, tzinfo=timezone.utc)  # 2025-05-01 00:00 at fixed UTC+1

# synthetic reference stations: id, name, latitude offset (deg; ~111 km per degree), longitude, constant value, types
REFERENCE_STATIONS = [
    ("NL00001", "Test traffic", 0.009, LON, 14.0, "verkeer", "stad"),          # ~1 km
    ("NL00002", "Test background", 0.036, LON, 10.0, "achtergrond", "stad"),   # ~4 km
    ("NL00003", "Test far away", None, 4.48, 5.0, "achtergrond", "stad"),      # Rotterdam, outside any 5 km radius
]
REFERENCE_FIRST_DAY, REFERENCE_LAST_DAY = date(2025, 4, 30), date(2025, 5, 2)


def r_available() -> bool:
    return bool(shutil.which("Rscript")) and (AT_DIR / "funs" / "data_to_tool_fun.R").exists()


def write_reference(folder: Path) -> tuple[Path, Path]:
    """Three days of hourly PM2.5 (plus PM10 rows that must be ignored) in the Luchtmeetnet file layout."""
    rows = []
    for station, *_, value, _kind, _area in REFERENCE_STATIONS:
        for h in range(72):
            stamp = (pd.Timestamp("2025-04-30") + pd.Timedelta(hours=h)).strftime("%Y-%m-%dT%H:00:00+01:00")
            rows.append((station, "PM2.5", stamp, value))
            rows.append((station, "PM10", stamp, 99.0))
    measurements = folder / "reference_measurements.parquet"
    pd.DataFrame(rows, columns=["meetlocatie_id", "component", "begindatumtijd", "waarde"]).to_parquet(measurements)
    meta = pd.DataFrame([
        {"meetlocatie_id": s, "meetlocatie_naam": n, "meetlocatie_plaatsnaam": "Testdorp",
         "breedtegraad": 51.92 if dlat is None else LAT + dlat, "lengtegraad": lon, "hoogte": 0,
         "meetlocatie_begindatumtijd": "2020-01-01", "meetlocatie_einddatumtijd": None,
         "gebiedstype": area, "stationstype": kind}
        for s, n, dlat, lon, _, kind, area in REFERENCE_STATIONS])
    metadata = folder / "reference_station_metadata.csv"
    meta.to_csv(metadata, index=False)
    return measurements, metadata


def write_sensors(path: Path, kits: dict) -> Path:
    """kits: kit_id -> (lat_offset, hourly pm25_kal values (24, None allowed), hourly pm25_raw values)."""
    rows = []
    for kit, (dlat, kal, raw) in kits.items():
        for h in range(24):
            ts = DAY_START_UTC + pd.Timedelta(hours=h)
            rows.append((kit, ts, kal[h], raw[h], LAT + dlat, LON))
    pd.DataFrame(rows, columns=["kit_id", "timestamp_from", "pm25_kal", "pm25_raw", "latitude", "longitude"]) \
        .to_parquet(path)
    return path
