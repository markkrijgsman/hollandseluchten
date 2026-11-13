from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.geo import haversine_km
from app.main import app, get_service
from app.service import Pm25Service, Settings

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT.parent.parent / "HackathonHollandseLuchten" / "data"
AT_DIR = ROOT.parent.parent / "Analyse-Together"
LAT, LON = 52.3676, 4.9041
DAY = date(2025, 5, 1)


@pytest.fixture
def sensor_parquet(tmp_path):
    """Two kits on 2025-05-01 (UTC+1 day): A ~1 km away constant 20, B ~2 km away constant 10 with one 500 outlier."""
    rows = []
    for hour in range(24):
        ts = datetime(2025, 4, 30, 23, tzinfo=timezone.utc) + pd.Timedelta(hours=hour)
        rows.append(("A", ts, 20.0, LAT + 0.009, LON))
        rows.append(("B", ts, 500.0 if hour == 0 else 10.0, LAT + 0.018, LON))
    df = pd.DataFrame(rows, columns=["kit_id", "timestamp_from", "pm25_kal", "latitude", "longitude"])
    path = tmp_path / "data_sensors.parquet"
    df.to_parquet(path)
    return path


def make_client(sensor_path=None):
    settings = Settings(DATA / "reference_measurements.parquet", DATA / "reference_station_metadata.csv",
                        AT_DIR, sensor_path)
    app.dependency_overrides[get_service] = lambda: Pm25Service(settings)
    return TestClient(app)


def test_haversine():
    assert haversine_km(52.0, 5.0, 52.0, 5.0) == 0
    assert haversine_km(52.3676, 4.9041, 51.9244, 4.4777) == pytest.approx(57.7, abs=0.5)  # Amsterdam-Rotterdam


def test_reference_only():
    body = make_client().get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    assert body["basis"] == "reference_stations"
    assert body["uncertainty"] == 0
    assert 5 < body["pm25"] < 40
    assert body["audit"][3]["functions"][0] == "add_ref_kal"


def test_sensor_idw_uncertainty_and_outlier(sensor_parquet):
    body = make_client(sensor_parquet).get(
        "/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat(), "min_hours": 0}).json()
    assert body["basis"] == "sensors"
    a, b = body["sensors"]["stations"]
    assert (a["id"], b["id"]) == ("A", "B")
    assert a["daily_mean"] == 20 and b["daily_mean"] == 10  # the 500 outlier is removed by the cut-off
    assert b["valid_hours"] == 23
    # weights 1/1^2 : 1/2^2 -> 0.8 / 0.2 ; IDW = 0.8*20 + 0.2*10
    assert body["pm25"] == pytest.approx(18.0, abs=0.05)
    # sensor uncertainty: max(20%*value, 5.3) -> A: 5.3 (20%*20=4), B: 5.3 ; weighted = 5.3
    assert body["uncertainty"] == pytest.approx(5.3, abs=0.01)


def test_validation_and_no_data():
    client = make_client()
    assert client.get("/pm25", params={"lat": 48.85, "lon": 2.35, "date": "2025-05-01"}).status_code == 422
    assert client.get("/pm25", params={"lat": LAT, "lon": LON, "date": "2030-01-01"}).status_code == 404
