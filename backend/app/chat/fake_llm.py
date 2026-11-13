"""Rule-based stand-in for the LLM, so /chat works without an API key (demo and tests).

It speaks the same protocol as the real client, so the whole chat loop (tool calls, validation, audit) runs
unchanged. It understands only simple questions: a place or 'lat, lon', plus a date, a year, or nothing.
It is NOT a language model: wording is template-based and follow-ups only reuse the previous location.
"""
import json
import re
from datetime import date

MONTHS = {"january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"}
PLACE = re.compile(r"(?i:\b(?:in|at|near|bij|rond|nabij))\s+(?:de\s+)?([A-Z][\w'-]*(?:\s+[A-Z][\w'-]*)*)")
LATLON = re.compile(r"(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)")
COMPARE_WORDS = ("compare", "limit", "guideline", "who", "norm", "exceed", "above", "boven", "overschrij")
SERIES_WORDS = ("per day", "trend", "over time", "per hour", "hourly", "daily", "verloop", "per dag")


class FakeLLM:
    name = "fake (rule-based stub, no language model)"

    def create(self, *, system: str, messages: list[dict], tools: list[dict]) -> dict:
        idx = max(i for i, m in enumerate(messages) if m["role"] == "user" and isinstance(m["content"], str))
        question = messages[idx]["content"]
        # (tool_use, tool_result) pairs made so far in this turn
        turn = []
        for i in range(idx + 1, len(messages) - 1, 2):
            by_id = {b["tool_use_id"]: b for b in messages[i + 1]["content"]}
            turn += [(b, by_id[b["id"]]) for b in messages[i]["content"] if b["type"] == "tool_use"]
        done = {use["name"]: res for use, res in turn}

        if turn and turn[-1][1].get("is_error"):
            return _text(f"I could not get an answer: {turn[-1][1]['content']}")
        if turn and turn[-1][0]["name"] not in ("geocode", "stations"):
            return _text(_answer(turn[-1][0]["name"], json.loads(turn[-1][1]["content"])))

        # where?
        place = next((p for p in PLACE.findall(question) if p.lower() not in MONTHS), None)
        m = LATLON.search(question)
        if m:
            point = (float(m.group(1)), float(m.group(2)))
        elif "geocode" in done:
            cands = json.loads(done["geocode"]["content"])["candidates"]
            if not cands:
                return _text("I could not find that place. Can you give a city, neighbourhood or address?")
            point = (cands[0]["lat"], cands[0]["lon"])
        elif place:
            return _call("geocode", {"q": place})
        else:
            point = _previous_point(messages[:idx])
            if point is None:
                return _text("Where do you want to know the air quality? Give a place name, address or coordinates.")

        # when?
        period = _period(question)
        if period is None and "stations" in done:  # no period given: latest day any nearby station has data
            stations = json.loads(done["stations"]["content"])["stations"]
            if not stations:
                return _text("There are no measuring stations within 5 km of that location.")
            last_day = date.fromisoformat(max(st["data_to"] for st in stations))
            period = (last_day, last_day)
        if period is None:
            return _call("stations", {"lat": point[0], "lon": point[1]})

        start, end = period
        low = question.lower()
        base = {"lat": point[0], "lon": point[1]}
        if start == end and not any(w in low for w in COMPARE_WORDS + SERIES_WORDS):
            return _call("pm25", {**base, "date": start.isoformat()})
        if any(w in low for w in SERIES_WORDS):
            return _call("pm25_timeseries", {**base, "from": start.isoformat(), "to": end.isoformat(),
                                             "resolution": "hour" if "hour" in low else "day"})
        return _call("pm25_compare", {**base, "from": start.isoformat(), "to": end.isoformat(),
                                      "against": "eu" if re.search(r"\beu\b", low) else "who"})


def _previous_point(earlier: list[dict]):
    for msg in reversed(earlier):
        if msg["role"] == "assistant":
            for b in msg["content"]:
                if b["type"] == "tool_use" and "lat" in b["input"]:
                    return b["input"]["lat"], b["input"]["lon"]
    return None


def _period(question: str):
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", question)
    if m:
        d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return d, d
    m = re.search(r"\b(20\d\d)\b", question)
    if m:
        return date(int(m.group(1)), 1, 1), date(int(m.group(1)), 12, 31)
    if "last year" in question.lower():
        y = date.today().year - 1
        return date(y, 1, 1), date(y, 12, 31)
    return None


def _text(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


_n = 0


def _call(name: str, args: dict) -> dict:
    global _n
    _n += 1
    return {"content": [{"type": "tool_use", "id": f"fake_{_n}", "name": name, "input": args}]}


def _answer(tool: str, r: dict) -> str:
    lim = r["limitations"][0] if r.get("limitations") else ""
    if tool == "pm25":
        basis = "Hollandse Luchten sensors" if r["basis"] == "sensors" else "official Luchtmeetnet stations"
        return (f"On {r['date']} the PM2.5 level near this location was about {r['pm25']} µg/m³ "
                f"(± {r['uncertainty']}), based on {basis}. {lim}")
    if tool == "pm25_compare":
        s, parts = r["summary"], []
        for c in r["comparisons"]:
            if c["type"] == "daily":
                parts.append(f"{c['days_above']} of {c['days_with_data']} days were above {c['name']} ({c['limit']} µg/m³)")
            else:
                verdict = "above" if c["exceeded"] else "below"
                parts.append(f"the period mean of {c['period_mean']} µg/m³ is {verdict} {c['name']} ({c['limit']} µg/m³)")
        return f"Between the given dates: {'; '.join(parts)}. {lim}"
    if tool == "pm25_timeseries":
        s = r["summary"]
        return (f"Over {s['periods_with_data']} periods the mean PM2.5 was {s['mean']} µg/m³ "
                f"(min {s['min']}, max {s['max']}). {lim}")
    return json.dumps(r)[:300]
