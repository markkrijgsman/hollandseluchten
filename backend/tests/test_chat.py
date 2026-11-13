"""Chat layer tests. The LLM is faked (rule-based stub or a scripted client), so no API key is needed."""
import os

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import app.tools.registry as tools_module
from app.chat import FakeChatModel, get_chat_model
from app.chat.tools import build_tools, for_model
from app.main import app
from helpers import DAY, LAT, LON

AMSTERDAM = [{"name": "Amsterdam", "type": "woonplaats", "lat": LAT, "lon": LON}]


@pytest.fixture
def client(make_client, sensor_parquet, monkeypatch):
    monkeypatch.setattr(tools_module, "geocode", lambda q, limit=5: AMSTERDAM)
    c = make_client(sensor_parquet)
    app.dependency_overrides[get_chat_model] = lambda: FakeChatModel()
    yield c
    app.dependency_overrides.pop(get_chat_model, None)


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
    class Scripted(GenericFakeChatModel):
        seen: list = []

        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, *a, **k):
            self.seen.append(list(messages))
            return super()._generate(messages, *a, **k)

    replies = iter([  # coordinate outside NL, then the model apologises
        AIMessage(content="", tool_calls=[{"name": "pm25", "id": "t1", "args": {"lat": 10, "lon": 4.9, "date": str(DAY)}}]),
        AIMessage(content="Sorry, that is outside the Netherlands."),
    ])
    model = Scripted(messages=replies)
    app.dependency_overrides[get_chat_model] = lambda: model
    body = ask(client, "air at lat 10")
    assert body["interpretation"][0]["error"].startswith("Invalid input")
    assert body["results"] == [] and body["answer"].startswith("Sorry")
    assert "outside the Netherlands" in model.seen[1][-1].content  # the tool error reached the model


def test_model_sees_summary_not_audit_or_long_series():
    env = {"audit": [1], "series": list(range(100)), "summary": {"mean": 1}, "request": {}}
    seen = for_model(env)
    assert "audit" not in seen and "omitted" in seen["series"] and seen["summary"] == {"mean": 1}
    assert env["audit"] == [1] and len(env["series"]) == 100  # the client still gets everything


def test_tools_are_exposed_with_schemas():
    tools = {t.name: t for t in build_tools(None)}
    assert set(tools) == {"geocode", "coverage", "stations", "pm25", "pm25_timeseries", "pm25_compare"}
    assert "from" in tools["pm25_compare"].args_schema["properties"]
    assert tools["pm25_compare"].description.startswith("Compare")


def test_get_chat_model_falls_back_to_stub_without_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HL_LLM", raising=False)
    assert isinstance(get_chat_model(), FakeChatModel)


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY (live OpenAI call)")
def test_live_openai(client, monkeypatch):
    monkeypatch.setenv("HL_LLM", "openai")
    app.dependency_overrides[get_chat_model] = get_chat_model
    body = ask(client, f"What was the PM2.5 in Amsterdam on {DAY}?")
    assert body["results"] and body["answer"]
