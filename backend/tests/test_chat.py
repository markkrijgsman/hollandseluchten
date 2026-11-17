"""Chat layer tests. The LLM is faked (rule-based stub or a scripted client), so no API key is needed."""
import os

import pytest
from fake_chat_model import FakeChatModel
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

import app.tools.registry as tools_module
from app.chat import get_chat_model
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


def test_model_sees_considerations_once():
    env = {"audit": [1], "limitations": ["x"], "considerations": [{"code": "c", "level": "caution", "message": "x"}]}
    seen = for_model(env)
    assert seen["considerations"] and "limitations" not in seen and "audit" not in seen
    assert for_model({"limitations": ["x"]})["limitations"] == ["x"]  # tools without considerations keep theirs


def test_stub_answer_mentions_cautions(client):
    body = ask(client, f"How polluted was the air in Amsterdam on {DAY}?")
    cautions = [c["message"] for c in body["results"][1]["considerations"] if c["level"] != "info"]
    assert all(m in body["answer"] for m in cautions)


def test_tools_are_exposed_with_schemas():
    tools = {t.name: t for t in build_tools(None)}
    assert set(tools) == {"geocode", "coverage", "stations", "pm25", "pm25_timeseries", "pm25_compare", "pm25_weekday",
                          "pm25_trend", "pm25_events"}
    assert "from" in tools["pm25_compare"].args_schema["properties"]
    assert tools["pm25_compare"].description.startswith("Compare")
    for t in tools.values():
        raw = str(t.args_schema)
        assert "exclusiveMinimum" not in raw and "'title'" not in raw and "'default'" not in raw


def test_chat_answers_503_without_api_key(make_client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    app.dependency_overrides.pop(get_chat_model, None)
    r = make_client().post("/chat", json={"message": "hi"})
    assert r.status_code == 503 and "OPENAI_API_KEY" in r.json()["detail"]


@pytest.mark.live
@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="needs OPENAI_API_KEY (live OpenAI call)")
def test_live_openai(client):
    app.dependency_overrides[get_chat_model] = get_chat_model
    body = ask(client, f"What was the PM2.5 in Amsterdam on {DAY}?")
    assert body["results"] and body["answer"]


def test_several_places_uses_the_first_and_says_so(client, monkeypatch):
    places = [{"name": "Haarlem", "type": "woonplaats", "lat": LAT, "lon": LON},
              {"name": "Haarlem, Groningen", "type": "woonplaats", "lat": 53.2, "lon": 6.5}]
    monkeypatch.setattr(tools_module, "geocode", lambda q, limit=5: places)
    body = ask(client, f"How polluted was the air in Haarlem on {DAY}?")
    assert body["interpretation"][1]["input"]["lat"] == LAT  # the first match
    note = body["results"][0]["considerations"][0]
    assert note["code"] == "ambiguous_place" and note["facts"]["place_chosen"] == "Haarlem"
    analysis = body["results"][1]
    assert analysis["considerations"][0]["code"] == "ambiguous_place"
    assert analysis["limitations"][0].startswith("'Haarlem' matched 2 places")
    assert "Haarlem, Groningen" in body["answer"]  # the stub passes the note on to the resident


def test_single_place_has_no_ambiguity_note(client):
    body = ask(client, f"How polluted was the air in Amsterdam on {DAY}?")
    assert body["results"][0]["considerations"] == [] and body["results"][0]["chosen"]["name"] == "Amsterdam"
    assert "ambiguous_place" not in {c["code"] for c in body["results"][1]["considerations"]}
