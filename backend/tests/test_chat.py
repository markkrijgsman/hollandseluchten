"""Chat layer tests. The LLM is faked (rule-based stub or a scripted client), so no API key is needed."""
import os

import pytest

import app.tools as tools_module
from app.chat import chat as run_chat, ChatRequest, _for_model, get_llm, tool_specs
from app.fake_llm import FakeLLM
from app.main import app
from test_api import DAY, LAT, LON, make_client, sensor_parquet  # noqa: F401

AMSTERDAM = [{"name": "Amsterdam", "type": "woonplaats", "lat": LAT, "lon": LON}]


@pytest.fixture
def client(sensor_parquet, monkeypatch):  # noqa: F811
    monkeypatch.setattr(tools_module, "geocode", lambda q, limit=5: AMSTERDAM)
    c = make_client(sensor_parquet)
    app.dependency_overrides[get_llm] = lambda: FakeLLM()
    yield c
    app.dependency_overrides.pop(get_llm, None)


def ask(client, message, history=()):
    r = client.post("/chat", json={"message": message, "history": list(history)})
    assert r.status_code == 200, r.text
    return r.json()


def test_question_runs_geocode_then_analysis_with_audit(client):
    body = ask(client, f"How polluted was the air in Amsterdam on {DAY}?")
    assert [c["tool"] for c in body["interpretation"]] == ["geocode", "pm25"]
    result = body["results"][1]
    assert str(result["pm25"]) in body["answer"]  # the answer quotes the tool's number
    assert result["audit"] and result["reproduce"].startswith("/pm25?")
    assert body["interpretation"][1]["reproduce"] == result["reproduce"]
    assert body["clarifying_question"] is None and body["llm"].startswith("fake")


def test_follow_up_reuses_location_from_history(client):
    first = ask(client, f"How polluted was the air in Amsterdam on {DAY}?")
    second = ask(client, "And on 2025-05-02?", first["history"])
    assert [c["tool"] for c in second["interpretation"]] == ["pm25"]
    assert second["interpretation"][0]["input"]["lat"] == LAT


def test_missing_place_gives_clarifying_question_and_runs_nothing(client):
    body = ask(client, "How polluted is the air?")
    assert body["clarifying_question"] and body["results"] == [] and body["interpretation"] == []


def test_no_period_uses_latest_covered_day(client):
    body = ask(client, "How is the air now in Amsterdam?")
    assert [c["tool"] for c in body["interpretation"]] == ["geocode", "stations", "pm25"]
    latest = max(st["data_to"] for st in body["results"][1]["stations"])
    assert body["results"][2]["date"] == latest  # nearby stations, not the dataset-wide end date


def test_year_question_compares_with_guideline(client):
    body = ask(client, "Compare the air in Amsterdam in 2025 with the WHO guideline")
    assert body["interpretation"][-1]["tool"] == "pm25_compare"
    assert body["interpretation"][-1]["input"]["against"] == "who"
    assert "days were above" in body["answer"]


def test_invalid_tool_input_is_reported_back_to_the_model(client):
    class Scripted:
        name = "scripted"

        def __init__(self):
            self.calls = []

        def create(self, *, system, messages, tools):
            self.calls.append(list(messages))
            if len(self.calls) == 1:  # coordinate outside NL
                return {"content": [{"type": "tool_use", "id": "t1", "name": "pm25",
                                     "input": {"lat": 10, "lon": 4.9, "date": str(DAY)}}]}
            return {"content": [{"type": "text", "text": "Sorry, that is outside the Netherlands."}]}

    llm = Scripted()
    app.dependency_overrides[get_llm] = lambda: llm
    body = ask(client, "air at lat 10")
    assert body["interpretation"][0]["error"].startswith("Invalid input")
    assert body["results"] == [] and body["answer"].startswith("Sorry")
    seen = llm.calls[1][-1]["content"][0]
    assert seen["is_error"] is True and "outside the Netherlands" in seen["content"]


def test_model_sees_summary_not_audit_or_long_series():
    env = {"audit": [1], "series": list(range(100)), "summary": {"mean": 1}, "request": {}}
    seen = _for_model(env)
    assert "audit" not in seen and "omitted" in seen["series"] and seen["summary"] == {"mean": 1}
    assert env["audit"] == [1] and len(env["series"]) == 100  # the client still gets everything


def test_tools_are_exposed_with_schemas():
    specs = {s["name"]: s for s in tool_specs()}
    assert set(specs) == {"geocode", "coverage", "stations", "pm25", "pm25_timeseries", "pm25_compare"}
    assert "from" in specs["pm25_compare"]["input_schema"]["properties"]


def test_get_llm_falls_back_to_stub_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("HL_LLM", raising=False)
    assert isinstance(get_llm(), FakeLLM)


@pytest.mark.skipif(not os.environ.get("ANTHROPIC_API_KEY"), reason="needs ANTHROPIC_API_KEY (live Claude call)")
def test_live_claude(client):
    from app.chat import AnthropicLLM
    app.dependency_overrides[get_llm] = lambda: AnthropicLLM()
    body = ask(client, f"What was the PM2.5 in Amsterdam on {DAY}?")
    assert body["results"] and body["answer"]
