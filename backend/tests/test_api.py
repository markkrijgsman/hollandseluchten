"""HTTP-level tests on synthetic data (see helpers.py). Real hackathon data: test_real_data.py."""
import pytest

from app.analysis.geo import haversine_km
from helpers import DAY, LAT, LON


def test_haversine():
    assert haversine_km(52.0, 5.0, 52.0, 5.0) == 0
    assert haversine_km(52.3676, 4.9041, 51.9244, 4.4777) == pytest.approx(57.7, abs=0.5)  # Amsterdam-Rotterdam


def test_reference_only_weights_stations_and_ignores_other_components_and_far_stations(make_client):
    body = make_client().get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    assert body["basis"] == "reference_stations" and body["sensors"] is None
    stations = body["reference"]["stations"]
    assert [s["id"] for s in stations] == ["NL00001", "NL00002"]  # NL00003 (Rotterdam) is outside the radius
    d1, d2 = (haversine_km(LAT, LON, LAT + off, LON) for off in (0.009, 0.036))
    w1, w2 = 1 / max(d1, 0.5) ** 2, 1 / max(d2, 0.5) ** 2
    assert body["pm25"] == pytest.approx((14 * w1 + 10 * w2) / (w1 + w2), abs=0.01)  # PM10 rows (99) are not used
    assert body["uncertainty"] == 0
    assert next(a for a in body["audit"] if a["action"].startswith("R:"))["functions"][0] == "add_ref_kal"


def test_sensor_idw_uncertainty_and_outlier(make_client, sensor_parquet):
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


def test_validation_and_no_data(make_client):
    client = make_client()
    assert client.get("/pm25", params={"lat": 48.85, "lon": 2.35, "date": "2025-05-01"}).status_code == 422
    assert client.get("/pm25", params={"lat": LAT, "lon": LON, "date": "2030-01-01"}).status_code == 404


def test_audit_reports_what_r_ran_and_versions(make_client, sensor_parquet):
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


def test_timeseries_matches_daily_and_hourly(make_client, sensor_parquet):
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


def test_timeseries_validation(make_client, sensor_parquet):
    client = make_client(sensor_parquet)
    base = {"lat": LAT, "lon": LON}
    assert client.get("/pm25/timeseries", params={**base, "from": "2025-05-02", "to": "2025-05-01"}).status_code == 422
    assert client.get("/pm25/timeseries", params={**base, "from": "2025-01-01", "to": "2025-03-01",
                                                  "resolution": "hour"}).status_code == 422


def test_compare_counts_days_above_limit(make_client, sensor_parquet):
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


def test_guidelines_come_from_config_file(make_client, tmp_path, monkeypatch):
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


def test_coverage_and_stations(make_client, sensor_parquet):
    client = make_client(sensor_parquet)
    cov = client.get("/coverage").json()
    assert (cov["reference_stations"]["from"], cov["reference_stations"]["to"]) == ("2025-04-30", "2025-05-02")
    assert cov["reference_stations"]["stations"] == 3
    assert cov["sensors"]["stations"] == 2 and cov["sensors"]["from"] == "2025-05-01"
    st = client.get("/stations", params={"lat": LAT, "lon": LON, "radius_km": 3}).json()
    kits = [s for s in st["stations"] if s["kind"] == "sensor"]
    assert [k["id"] for k in kits] == ["A", "B"] and kits[0]["distance_km"] < kits[1]["distance_km"]
    traffic = next(s for s in st["stations"] if s["id"] == "NL00001")
    assert traffic["station_type"] == "verkeer" and traffic["data_to"] == "2025-05-02"
    assert st["stations"] == sorted(st["stations"], key=lambda s: s["distance_km"])
    assert client.get("/stations", params={"lat": 10, "lon": 10}).status_code == 422


def test_geocode(make_client, monkeypatch):
    import app.tools.registry as t
    monkeypatch.setattr(t, "geocode", lambda q, limit: [{"name": "Jordaan, Amsterdam", "type": "wijk", "lat": 52.37, "lon": 4.88}])
    body = make_client().get("/geocode", params={"q": "Jordaan"}).json()
    assert body["candidates"][0]["lat"] == 52.37 and body["chosen"] == body["candidates"][0]
    assert body["considerations"] == []


def test_geocode_parses_pdok_point(monkeypatch):
    import app.integrations.pdok as g

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"response": {"docs": [{"weergavenaam": "X", "type": "wijk", "centroide_ll": "POINT(4.88 52.37)"}]}}
    monkeypatch.setattr(g.httpx, "get", lambda *a, **k: Resp())
    assert g.geocode("x") == [{"name": "X", "type": "wijk", "lat": 52.37, "lon": 4.88}]


def test_reproduce_url_returns_same_result(make_client, sensor_parquet):
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


RANGE = {"lat": LAT, "lon": LON, "from": "2025-04-30", "to": "2025-05-02"}  # Wed-Fri in the synthetic reference data


def test_weekday_without_weekend_days_has_empty_group_and_a_caution(make_client):
    body = make_client().get("/pm25/weekday", params=RANGE).json()
    assert body["weekday"]["n_days"] == 3 and body["weekday"]["mean"] is not None
    assert body["weekend"] == {"n_days": 0, "mean": None, "min": None, "max": None} and body["difference"] is None
    assert "few_weekend_days" in {c["code"] for c in body["considerations"]}
    step = next(s for s in body["audit"] if s["code"] == "weekday_split")
    assert step["weekend_days"] == 0 and "weekend_mean" not in step


def test_trend_is_stable_on_flat_data_and_says_it_rests_on_few_days(make_client):
    body = make_client().get("/pm25/trend", params=RANGE).json()
    assert body["direction"] == "stable" and body["slope_ug_m3_per_day"] == 0 and body["n_days"] == 3
    codes = {c["code"] for c in body["considerations"]}
    assert {"trend_is_a_line", "trend_few_points"} <= codes
    assert next(s for s in body["audit"] if s["code"] == "linear_trend")["stable_below"] == 0.005


def test_events_lists_days_at_or_above_threshold(make_client):
    client = make_client()
    body = client.get("/pm25/events", params={**RANGE, "threshold": 13}).json()
    assert body["n_events"] == 3 and body["n_days_with_data"] == 3 and body["share_above"] == 1.0
    assert [e["date"] for e in body["events"]] == ["2025-04-30", "2025-05-01", "2025-05-02"]
    assert client.get("/pm25/events", params={**RANGE, "threshold": 50}).json()["events"] == []
    assert {"events_are_daily_means"} <= {c["code"] for c in body["considerations"]}


def test_guidelines_norms_come_from_the_guideline_sets(make_client):
    body = make_client().get("/guidelines").json()
    assert {k: body[k] for k in ("who", "eu2030", "euNow", "who_daily")} == {"who": 5, "eu2030": 10, "euNow": 25,
                                                                          "who_daily": 15}
    assert body["verified"] == {"who": False, "eu2030": False, "euNow": True, "who_daily": False}


def test_guidelines_fails_loudly_when_a_norm_is_missing(make_client, tmp_path, monkeypatch):
    f = tmp_path / "g.toml"
    f.write_text('[[levels.x]]\nid="a"\nnorm="who"\nname="n"\ntype="annual"\nlimit=5\nsource="s"\nverified=true\n')
    monkeypatch.setenv("HL_GUIDELINES_FILE", str(f))
    r = make_client().get("/guidelines")
    assert r.status_code == 503 and "eu2030" in r.json()["detail"]


def test_events_use_strictly_above_like_compare(make_client):
    client = make_client()
    day = client.get("/pm25", params={"lat": LAT, "lon": LON, "date": "2025-05-01"}).json()["pm25"]
    at_limit = client.get("/pm25/events", params={**RANGE, "threshold": day}).json()
    assert "2025-05-01" not in [e["date"] for e in at_limit["events"]]  # equal to the threshold is not above it
