# Language & Tooling Recommendation: Challenge 3

## Context

Challenge 3 requires an LLM-powered agent that lets residents ask natural-language questions about air quality, runs appropriate analyses, and returns results with a full audit trail. The existing R codebase (Analyse-Together / openair) is available as a reference for the analysis logic. No code exists in the repo yet.

## Recommendation: Python

### Why Python over R or TypeScript

- **R**: The existing Analyse-Together codebase is R, but LLM tool-use integration in R is immature. Wrapping R from Python via subprocess is straightforward if needed.
- **TypeScript**: Strong for frontends but weak for time-series data analysis.
- **Python**: Best-in-class on all three pillars simultaneously — LLM integration, data analysis, and API clients.

### Core stack

| Layer | Library | Rationale |
|---|---|---|
| LLM + tool use | `anthropic` SDK (Claude) | Native tool-calling maps directly to the audit-trail requirement — each tool call is a logged step |
| UI | `streamlit` | Fastest hackathon path to a working demo; chat + chart in one file |
| Data analysis | `pandas`, `numpy` | Time-series filtering, groupby (weekday/weekend), outlier removal |
| Visualizations | `plotly` | Interactive pollution roses, time-series, bar charts — all in browser |
| API client | `httpx` | Async-friendly calls to Samen Meten API and KNMI |
| R interop (optional) | `subprocess` | Call Analyse-Together R functions if reimplementing is too slow |

### Architecture: Claude with tool use

The audit-trail requirement is the key design driver. Claude's tool-use loop produces a natural audit trail for free:

```
User question
  → Claude decides which tool to call (e.g. get_sensor_data, compute_pollution_rose)
  → Tool executes, returns structured result
  → Claude calls next tool or explains result
  → All tool calls + inputs/outputs = audit trail
```

Suggested tools to expose to the agent:
- `get_sensor_data(sensor_ids, start, end)` — Samen Meten API
- `get_reference_data(station_id, start, end)` — Luchtmeetnet API
- `get_weather_data(start, end)` — KNMI API
- `filter_outliers(data, max_value)` — default 100 μg/m³
- `compute_pollution_rose(data, weather)` — wind direction × PM2.5
- `compare_time_groups(data, groupby)` — weekday/weekend, hour-of-day
- `plot_timeseries(data)` — returns plotly figure

### RAG (lightweight)

For metadata lookup (sensor locations, which sensors are near a given address), embed the sensor metadata CSV at startup with `sentence-transformers` + cosine similarity — no vector DB needed for a hackathon.

### Model choice

Use `claude-sonnet-4-5` (fast, cheap) for development; switch to `claude-opus-4-5` for the demo if reasoning quality needs improvement.

## Verification

End-to-end test with the two resident questions from QUESTIONS.md:
1. "How does air quality relate to wind direction?" → should call `get_sensor_data` + `get_weather_data` + `compute_pollution_rose`
2. "Is air quality worse on weekdays vs. weekends?" → should call `get_sensor_data` + `compare_time_groups`

Check that every tool call appears in the rendered audit trail in the Streamlit UI.
