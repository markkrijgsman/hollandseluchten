"""Considerations: rules in config/considerations.toml evaluated against facts about a run."""
import pytest

from app.analysis.considerations import evaluate, load_rules
from app.analysis.facts import FACTS
from helpers import DAY, LAT, LON

RULES = load_rules()
BASE = {"single_period": True, "resolution": "day", "sensor_periods": 0, "sensors_configured": True,
        "outlier_cutoff": 100.0, "outliers_removed": 0, "hourly_values_in": 100, "outlier_share": 0.0,
        "stations_excluded": 0, "min_stations": 3, "max_share": 0.4, "nearest_km": 1.0, "uncertainty_ratio": 0.1,
        "periods": 1, "periods_expected": 1, "periods_without_data": 0, "periods_on_reference": 1, "basis": "reference_stations"}


def codes(facts, scope="run"):
    return [c.code for c in evaluate(RULES, facts, scope)]


def test_shipped_rules_load_and_only_use_known_facts():
    assert len(RULES) == len({r["code"] for r in RULES})
    assert {c["fact"] for r in RULES for c in r["when"]} <= FACTS.keys()


def test_rules_react_to_the_facts():
    assert "outliers_removed" not in codes(BASE)
    some = {**BASE, "outliers_removed": 3, "outlier_share": 0.03}
    assert "outliers_removed" in codes(some) and "many_outliers" not in codes(some)
    assert "many_outliers" in codes({**some, "outlier_share": 0.2})
    assert "single_station" in codes({**BASE, "min_stations": 1})
    assert "far_from_stations" in codes({**BASE, "nearest_km": 3.5})
    assert "dominant_station" in codes({**BASE, "max_share": 0.8})
    assert "dominant_station" not in codes({**BASE, "min_stations": 1, "max_share": 1.0})  # single station covers it
    assert "daily_mean" in codes(BASE) and "daily_mean" not in codes({**BASE, "single_period": False})


def test_message_is_filled_from_facts_and_the_facts_are_returned():
    c = next(c for c in evaluate(RULES, {**BASE, "nearest_km": 3.46}) if c.code == "far_from_stations")
    assert "3.5 km" in c.message and c.facts == {"nearest_km": 3.46}
    assert c.level == "caution" and c.origin == "this-api"


def test_rule_with_a_missing_fact_does_not_apply():
    assert "high_relative_uncertainty" not in codes({**BASE, "uncertainty_ratio": None})


def test_level_scope_rules_run_per_level():
    annual = {"level_name": "L", "level_type": "annual", "level_limit": 5, "level_verified": False, "period_days": 31,
              "days_with_data": 31, "period_mean": 6.0, "mean_uncertainty": 2.0, "level_uncertain": True}
    assert set(codes(annual, "level")) == {"level_not_verified", "partial_year", "annual_within_uncertainty"}
    daily = {**annual, "level_type": "daily", "level_verified": True, "ambiguous_days": 4, "level_uncertain": None}
    assert codes(daily, "level") == ["daily_within_uncertainty"]


def write(tmp_path, body):
    f = tmp_path / "r.toml"
    f.write_text(body)
    return f


@pytest.mark.parametrize("body, problem", [
    ('[[rule]]\ncode="a"\nlevel="info"\norigin="this-api"\nmessage="{nope}"', "unknown facts"),
    ('[[rule]]\ncode="a"\nlevel="info"\norigin="this-api"\nmessage="x"\nwhen=[{fact="nope",op=">",value=1}]', "unknown facts"),
    ('[[rule]]\ncode="a"\nlevel="loud"\norigin="this-api"\nmessage="x"', "invalid level"),
    ('[[rule]]\ncode="a"\nlevel="info"\norigin="me"\nmessage="x"', "invalid level, origin"),
    ('[[rule]]\ncode="a"\nlevel="info"\norigin="this-api"\nmessage="{level_name}"', "per-level or per-place facts"),
    ('[[rule]]\ncode="a"\nlevel="info"\norigin="this-api"\nmessage="x"\n[[rule]]\ncode="a"\nlevel="info"\n'
     'origin="this-api"\nmessage="y"', "twice"),
])
def test_invalid_rule_files_are_rejected(tmp_path, body, problem):
    with pytest.raises(ValueError, match=problem):
        load_rules(write(tmp_path, body))


def test_api_returns_considerations_with_origin_and_matching_limitations(make_client, sensor_parquet):
    body = make_client(sensor_parquet).get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    by_code = {c["code"]: c for c in body["considerations"]}
    assert by_code["sensor_uncertainty"]["origin"] == "analyse-together"
    assert by_code["sensor_uncertainty"]["facts"] == {"sensor_periods": 1, "sensor_uncertainty_percent": 20,
                                                      "sensor_uncertainty_min": 5.3}
    assert by_code["outliers_removed"]["facts"]["outliers_removed"] == 1  # the 500 reading of kit B
    assert body["limitations"] == [c["message"] for c in body["considerations"]]


def test_considerations_file_can_be_replaced(make_client, tmp_path, monkeypatch):
    f = write(tmp_path, '[[rule]]\ncode="only"\nlevel="warning"\norigin="config"\nmessage="{periods} period"')
    monkeypatch.setenv("HL_CONSIDERATIONS_FILE", str(f))
    body = make_client().get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    assert [(c["code"], c["message"]) for c in body["considerations"]] == [("only", "1 period")]


def test_audit_steps_are_typed_and_numbered(make_client, sensor_parquet):
    body = make_client(sensor_parquet).get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    assert [s["step"] for s in body["audit"]] == list(range(1, len(body["audit"]) + 1))
    assert [s["code"] for s in body["audit"]] == ["request", "select_stations", "select_stations", "r_functions",
                                                  "station_means", "weighted_mean", "versions"]
    sensors = body["audit"][2]
    assert sensors["kind"] == "sensor" and sensors["stations"] == ["A", "B"]  # no internal prefix
    assert "date" in body["audit"][0] and "start" not in body["audit"][0]     # empty fields are left out


def test_station_type_is_reported_where_it_matters(make_client):
    body = make_client().get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    by_code = {c["code"]: c for c in body["considerations"]}
    # synthetic reference: traffic station at ~1 km (value 14) outweighs the background station at ~4 km
    assert by_code["traffic_station_dominates"]["level"] == "caution"
    assert by_code["traffic_station_dominates"]["facts"]["traffic_weight_share"] > 0.9
    assert "sensor_type_unknown" not in by_code and "industry_station_used" not in by_code
    select = next(s for s in body["audit"] if s["code"] == "select_stations" and s["kind"] == "reference")
    assert select["station_types"] == {"NL00001": "verkeer", "NL00002": "achtergrond"}


def test_sensors_have_no_station_type(make_client, sensor_parquet):
    body = make_client(sensor_parquet).get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    codes_ = {c["code"] for c in body["considerations"]}
    assert "sensor_type_unknown" in codes_ and not codes_ & {"traffic_station_dominates", "traffic_station_used"}


def test_audit_numbers_and_considerations_come_from_the_same_facts(make_client, sensor_parquet):
    body = make_client(sensor_parquet).get("/pm25", params={"lat": LAT, "lon": LON, "date": DAY.isoformat()}).json()
    r = next(s for s in body["audit"] if s["code"] == "r_functions")
    removed = next(c for c in body["considerations"] if c["code"] == "outliers_removed")["facts"]
    assert (r["outliers_removed"], r["hourly_values_in"]) == (removed["outliers_removed"], removed["hourly_values_in"])
