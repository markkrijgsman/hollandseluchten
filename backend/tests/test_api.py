from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.analysis.geo import haversine_km
from app.main import app, get_service
from app.analysis.service import Pm25Service
from app.settings import Settings

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


def test_audit_reports_what_r_ran_and_versions(sensor_parquet):
    body = make_client(sensor_parquet).get(
        "/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    r_step = next(a for a in body["audit"] if a["action"].startswith("R:"))
    assert r_step["functions"] == ["add_ref_kal", "outlier cut-off (value < cutoff)", "add_uncertainty_sensor_percent"]
    # parameters are read back from the R function defaults, not typed in Python
    assert r_step["parameters"] == {"outlier_cutoff": 100, "sensor_uncertainty_percent": 20,
                                    "sensor_uncertainty_min_ug_m3": 5.3}
    assert "20%" in body["limitations"][2] and "5.3" in body["limitations"][2]
    versions = next(a for a in body["audit"] if a["action"] == "versions")
    assert versions["reference_data"]["file"] == "reference_measurements.parquet"
    assert versions["sensor_data"]["covers"]["from"] == DAY.isoformat()
    assert "analyse_together_commit" in versions


def test_timeseries_matches_daily_and_hourly(sensor_parquet):
    client = make_client(sensor_parquet)
    params = {"lat": LAT, "lon": LON, "from": "2025-04-30", "to": DAY.isoformat()}
    daily = client.get("/pm25/timeseries", params=params).json()
    single = client.get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    point = next(p for p in daily["series"] if p["time"] == DAY.isoformat())
    assert point["pm25"] == single["pm25"] and point["basis"] == "sensors"
    assert daily["summary"]["periods_expected"] == 2
    hourly = client.get("/pm25/timeseries", params={**params, "from": DAY.isoformat(), "resolution": "hour"}).json()
    assert len(hourly["series"]) == 24 and hourly["series"][0]["time"] == "2025-05-01T00"
    # hour 0: kit B reads 500 (outlier, removed), so only kit A (20) remains
    assert hourly["series"][0]["pm25"] == 20.0


def test_timeseries_validation(sensor_parquet):
    client = make_client(sensor_parquet)
    base = {"lat": LAT, "lon": LON}
    assert client.get("/pm25/timeseries", params={**base, "from": "2025-05-02", "to": "2025-05-01"}).status_code == 422
    assert client.get("/pm25/timeseries", params={**base, "from": "2025-01-01", "to": "2025-03-01",
                                                  "resolution": "hour"}).status_code == 422


def test_compare_counts_days_above_limit(sensor_parquet):
    client = make_client(sensor_parquet)
    params = {"lat": LAT, "lon": LON, "from": DAY.isoformat(), "to": DAY.isoformat()}
    who = client.get("/pm25/compare", params=params).json()
    daily = next(c for c in who["comparisons"] if c["type"] == "daily")
    annual = next(c for c in who["comparisons"] if c["type"] == "annual")
    # fixture day mean is ~18 (weighted 20 and 10), above the WHO daily limit of 15
    assert daily["days_with_data"] == 1 and daily["days_above"] == 1
    assert annual["exceeded"] is True and annual["period_mean"] > 5
    assert any("only indicative" in lim for lim in who["limitations"])
    eu = client.get("/pm25/compare", params={**params, "against": "eu"}).json()
    assert eu["comparisons"][0]["limit"] == 25 and eu["comparisons"][0]["verified"] is True
    assert eu["comparisons"][0]["exceeded"] is False
    assert any(a["action"] == "compare with reference levels" for a in eu["audit"])


def test_guidelines_come_from_config_file(tmp_path, monkeypatch):
    f = tmp_path / "g.toml"
    f.write_text('''[[levels.test]]
id = "t"
name = "Test level"
type = "daily"
limit = 1
source = "test"
verified = true
''')
    monkeypatch.setenv("HL_GUIDELINES_FILE", str(f))
    client = make_client()
    body = client.get("/pm25/compare", params={"lat": LAT, "lon": LON, "from": "2025-05-01", "to": "2025-05-02",
                                               "against": "test"}).json()
    assert body["comparisons"][0]["id"] == "t" and body["comparisons"][0]["days_above"] == 2
    assert client.get("/pm25/compare", params={"lat": LAT, "lon": LON, "from": "2025-05-01", "to": "2025-05-02",
                                               "against": "who"}).status_code == 422


def test_coverage_and_stations(sensor_parquet):
    client = make_client(sensor_parquet)
    cov = client.get("/coverage").json()
    assert cov["reference_stations"]["from"] <= "2025-05-01" <= cov["reference_stations"]["to"]
    assert cov["sensors"]["stations"] == 2 and cov["sensors"]["from"] == "2025-05-01"
    st = client.get("/stations", params={"lat": LAT, "lon": LON, "radius_km": 3}).json()
    kits = [s for s in st["stations"] if s["kind"] == "sensor"]
    assert [k["id"] for k in kits] == ["A", "B"] and kits[0]["distance_km"] < kits[1]["distance_km"]
    assert st["stations"] == sorted(st["stations"], key=lambda s: s["distance_km"])
    assert client.get("/stations", params={"lat": 10, "lon": 10}).status_code == 422


def test_geocode(monkeypatch):
    import app.tools.registry as t
    monkeypatch.setattr(t, "geocode", lambda q, limit: [{"name": "Jordaan, Amsterdam", "type": "wijk", "lat": 52.37, "lon": 4.88}])
    body = make_client().get("/geocode", params={"q": "Jordaan"}).json()
    assert body["candidates"][0]["lat"] == 52.37


def test_geocode_parses_pdok_point(monkeypatch):
    import app.integrations.pdok as g

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"response": {"docs": [{"weergavenaam": "X", "type": "wijk", "centroide_ll": "POINT(4.88 52.37)"}]}}
    monkeypatch.setattr(g.httpx, "get", lambda *a, **k: Resp())
    assert g.geocode("x") == [{"name": "X", "type": "wijk", "lat": 52.37, "lon": 4.88}]


def test_reproduce_url_returns_same_result(sensor_parquet):
    client = make_client(sensor_parquet)
    first = client.get("/pm25/timeseries", params={"lat": LAT, "lon": LON, "from": "2025-05-01", "to": "2025-05-01"}).json()
    assert first["request"]["from"] == "2025-05-01" and first["request"]["resolution"] == "day"
    again = client.get(first["reproduce"]).json()
    assert again["series"] == first["series"] and again["reproduce"] == first["reproduce"]


def test_tool_schemas_are_usable_for_llm():
    from app.tools.registry import TOOLS
    schema = TOOLS["pm25_compare"].model.model_json_schema(by_alias=True)
    assert {"lat", "lon", "from", "to"} <= set(schema["required"]) | set(schema["properties"])
    assert TOOLS["pm25_compare"].description.startswith("Compare")
