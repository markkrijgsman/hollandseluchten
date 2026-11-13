"""Demonstrates: distance-weighted daily mean, use of calibrated data, use of the calibration flag."""
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

from app.data.repositories import SensorRepository
from app.analysis.geo import haversine_km
from app.integrations.r_bridge import run_r_analysis
from app.analysis.constants import MIN_DISTANCE_KM
from app.analysis.service import Pm25Service
from app.settings import Settings

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT.parent.parent / "HackathonHollandseLuchten" / "data"
AT_DIR = ROOT.parent.parent / "Analyse-Together"
LAT, LON = 52.3676, 4.9041
DAY = date(2025, 5, 1)
DAY_START_UTC = datetime(2025, 4, 30, 23, tzinfo=timezone.utc)  # 2025-05-01 00:00 at fixed UTC+1


def write_sensors(path: Path, kits: dict) -> Path:
    """kits: kit_id -> (lat_offset, hourly pm25_kal values (24 or None), hourly pm25_raw values)."""
    rows = []
    for kit, (dlat, kal, raw) in kits.items():
        for h in range(24):
            ts = DAY_START_UTC + pd.Timedelta(hours=h)
            rows.append((kit, ts, kal[h], raw[h], LAT + dlat, LON))
    pd.DataFrame(rows, columns=["kit_id", "timestamp_from", "pm25_kal", "pm25_raw", "latitude", "longitude"]) \
        .to_parquet(path)
    return path


def service(sensor_path: Path) -> Pm25Service:
    return Pm25Service(Settings(DATA / "reference_measurements.parquet",
                                DATA / "reference_station_metadata.csv", AT_DIR, sensor_path))


# ---------------------------------------------------------------- distance-weighted daily mean
def test_distance_weighted_daily_mean_step_by_step(tmp_path):
    """Hourly values -> daily mean per station -> 1/d^2 weights (distance floor 0.5 km) -> weighted mean."""
    flat = lambda v: [v] * 24
    # kit: (latitude offset in degrees (~111 km per degree), hourly kal, hourly raw)
    # N: ~0.1 km (below the 0.5 km floor), A: ~1 km, B: ~2 km, C: ~4 km
    kits = {"N": (0.0009, flat(40.0), flat(0.0)), "A": (0.009, flat(30.0), flat(0.0)),
            "B": (0.018, flat(20.0), flat(0.0)), "C": (0.036, flat(10.0), flat(0.0))}
    # kit A alternates 20/40 over the day -> daily mean must be 30
    kits["A"] = (0.009, [20.0, 40.0] * 12, flat(0.0))
    body = service(write_sensors(tmp_path / "s.parquet", kits)).compute(LAT, LON, DAY, radius_km=5)

    assert body["basis"] == "sensors"
    got = {s["id"]: s for s in body["sensors"]["stations"]}
    daily = {"N": 40.0, "A": 30.0, "B": 20.0, "C": 10.0}
    assert {k: v["daily_mean"] for k, v in got.items()} == daily  # step 1: daily mean per station

    # step 2: independent calculation of the weights from the kit coordinates
    dist = {k: haversine_km(LAT, LON, LAT + kits[k][0], LON) for k in kits}
    assert dist["N"] < MIN_DISTANCE_KM  # the floor applies to N
    raw_w = {k: 1 / max(d, MIN_DISTANCE_KM) ** 2 for k, d in dist.items()}
    expected = sum(daily[k] * raw_w[k] for k in kits) / sum(raw_w.values())

    assert body["pm25"] == pytest.approx(expected, abs=0.01)  # step 3: weighted mean
    assert sum(s["weight"] for s in got.values()) == pytest.approx(1.0, abs=0.01)
    assert got["N"]["weight"] > got["A"]["weight"] > got["B"]["weight"] > got["C"]["weight"]
    assert body["pm25"] > sum(daily.values()) / 4  # closer (higher) stations pull above the plain mean (25)


def test_station_with_too_few_hours_is_excluded(tmp_path):
    kits = {"A": (0.009, [20.0] * 24, [0.0] * 24),
            "B": (0.018, [100.0 - 1] * 10 + [None] * 14, [0.0] * 24)}  # only 10 valid hours
    body = service(write_sensors(tmp_path / "s.parquet", kits)).compute(LAT, LON, DAY, radius_km=5, min_hours=18)
    assert [s["id"] for s in body["sensors"]["stations"]] == ["A"]
    assert body["pm25"] == 20.0
    excluded = next(a for a in body["audit"] if a["action"] == "daily mean per station")["excluded_for_too_few_hours"]
    assert excluded == {"HL_B": 10}


# ---------------------------------------------------------------- calibrated data
def test_sensor_repository_returns_calibrated_not_raw(tmp_path):
    path = write_sensors(tmp_path / "s.parquet", {"A": (0.0, [12.0] * 24, [99.0] * 24)})
    df = SensorRepository(path).hourly(DAY)
    assert len(df) == 24
    assert set(df["value"]) == {12.0}  # pm25_kal, never pm25_raw (99)
    assert df["hour"].iloc[0] == "2025-05-01T00" and df["hour"].iloc[-1] == "2025-05-01T23"  # UTC+1 day


def test_hours_without_calibrated_value_are_not_used(tmp_path):
    kal = [15.0] * 20 + [None] * 4  # last 4 hours: raw exists, calibration missing
    path = write_sensors(tmp_path / "s.parquet", {"A": (0.0, kal, [80.0] * 24)})
    df = SensorRepository(path).hourly(DAY)
    assert len(df) == 20 and set(df["value"]) == {15.0}  # raw (80) is not substituted


def test_api_result_uses_calibrated_values(tmp_path):
    path = write_sensors(tmp_path / "s.parquet", {"A": (0.009, [12.0] * 24, [99.0] * 24)})
    body = service(path).compute(LAT, LON, DAY, radius_km=5)
    assert body["pm25"] == 12.0


# ---------------------------------------------------------------- calibration flag (R: add_ref_kal)
def r(rows, cutoff=100.0):
    return run_r_analysis(rows, cutoff, AT_DIR)


def row(station, parameter, value, date="2025-05-01T00"):
    return {"station": station, "parameter": parameter, "value": value, "date": date}


def test_reference_station_raw_value_becomes_calibrated_with_zero_uncertainty():
    """add_ref_kal: a reference 'pm25' value is flagged 'pm25_kal' (reference = already calibrated); sd = 0."""
    out = r([row("NL49017", "pm25", 15.2)])
    assert out["functions"][0] == "add_ref_kal"
    (res,) = out["rows"]
    assert res["parameter"] == "pm25_kal" and res["value"] == 15.2 and res["sd"] == 0


def test_sensor_calibrated_value_gets_uncertainty_and_raw_is_ignored():
    """Sensors are selected on the 'pm25_kal' flag; uncertainty = max(20% of value, 5.3 ug/m3)."""
    out = r([row("HL_A", "pm25_kal", 40.0), row("HL_B", "pm25_kal", 10.0), row("HL_A", "pm25", 99.0)])
    res = {x["station"]: x for x in out["rows"]}
    assert set(res) == {"HL_A", "HL_B"} and len(out["rows"]) == 2  # the raw 'pm25' row is dropped
    assert res["HL_A"]["sd"] == pytest.approx(8.0)  # 20% of 40
    assert res["HL_B"]["sd"] == pytest.approx(5.3)  # 20% of 10 = 2 -> minimum 5.3


def test_outlier_cutoff_applies_to_calibrated_values():
    out = r([row("HL_A", "pm25_kal", 150.0), row("HL_A", "pm25_kal", 50.0, "2025-05-01T01")], cutoff=100)
    assert out["removed_outliers"] == 1
    assert [x["value"] for x in out["rows"]] == [50.0]
