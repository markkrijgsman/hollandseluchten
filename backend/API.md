# PM2.5 API

Air-pollution (PM2.5) answers for residents, with an audit trail. Interactive docs (Swagger): http://localhost:8000/docs

| Endpoint | Purpose |
|---|---|
| `GET /geocode?q=` | Place or address to lat/lon candidates (PDOK Locatieserver) |
| `GET /coverage` | Date range and station counts of the data |
| `GET /stations?lat&lon&radius_km` | Nearby stations and the period they have data |
| `GET /pm25?lat&lon&date` | Distance-weighted (1/d², floor 0.5 km) daily mean PM2.5 (µg/m³) with uncertainty |
| `GET /pm25/timeseries?lat&lon&from&to&resolution=day\|hour` | The same per day (max 366 days) or hour (max 31 days) |
| `GET /pm25/compare?lat&lon&from&to&against=who\|eu` | Compare with reference levels from `config/guidelines.toml` |
| `POST /chat {message, history}` | Plain-language question; an LLM calls the endpoints above |

Every analysis response contains `considerations`, an `audit` list of steps, the resolved `request` and a `reproduce`
URL that reruns it. `limitations` repeats the considerations' messages as plain strings.

**Considerations** are notes derived from what happened in this run (outliers removed, stations left out, distance to
the nearest station, result within its uncertainty of a limit, ...). Each has a stable `code`, a `level`
(`info`/`caution`/`warning`), an `origin` (`analyse-together`, `this-api` or `config`: where the underlying choice
comes from; our own thresholds are `this-api`), an English `message` and the `facts` behind it. The rules, thresholds
and wording are in `config/considerations.toml` (override with `HL_CONSIDERATIONS_FILE`); the facts are recorded by
`analysis/facts.py`. Audit steps are typed (`code`: `request`, `select_stations`, `r_functions`, `station_means`,
`weighted_mean`, `compare`, `versions`), so Swagger documents their fields. Sensors (calibrated `pm25_kal`) are used when available, otherwise official Luchtmeetnet stations.
Calibration flag, uncertainty and outlier cut-off come from the Analyse-Together R functions (`r/analysis.R`).

## Code layout

```
app/
  main.py          routes only (uvicorn app.main:app)
  settings.py      paths from the environment
  analysis/        service.py      facade: compute, timeseries, compare, coverage, stations
                   pipeline.py     observations -> station means -> weighted estimates (shared by all analyses)
                   observations.py station selection + the R call
                   weighting.py    the distance-weighted mean (pure pandas)
                   facts.py (what happened in a run), considerations.py (rules engine), compare.py, catalog.py,
                   versions.py, audit.py (typed steps),
                   periods.py, constants.py, errors.py, geo.py, guidelines.py (config/guidelines.toml)
  data/            repositories.py (Luchtmeetnet and Hollandse Luchten parquet access)
  integrations/    r_bridge.py (Rscript + r/analysis.R), pdok.py (geocoder)
  analysis/models.py  typed responses (the Swagger response schemas)
  tools/           schemas.py (request models), responses.py, registry.py (tools shared by REST and chat)
  chat/            engine.py (agent run), tools.py (endpoints as LangChain tools), models.py, prompt.py
r/analysis.R       glue that sources Analyse-Together and applies its functions
config/            guidelines.toml, considerations.toml
```

## Chat

`POST /chat` returns `answer`, `clarifying_question`, `interpretation` (every tool call made), `results` (full
envelopes with audit), `suggestions`, `llm` and `history`. It is stateless: send `history` back for follow-ups.
The model only picks tools and words the answer; all numbers come from the tools.

It is a LangChain agent (`langchain.agents.create_agent`, on LangGraph) whose tools are the endpoints above
(`chat/tools.py`). The tool result goes to the model without audit; the full result goes to the client.

* It uses OpenAI (`HL_CHAT_MODEL`, default `gpt-4o`) and needs `OPENAI_API_KEY`; without it `/chat` answers 503.
* The tests use a rule-based stand-in (`tests/fake_llm.py`, `tests/fake_chat_model.py`). It is not a language model and is not part of the app.
* Any other LangChain chat model works: return it from `get_chat_model` in `chat/models.py`.

## Required project structure

The backend reads data and R code from sibling directories. Clone everything into one parent directory:

```
<parent>/
├── hollandseluchten/              # this repo
│   └── backend/                   # this API (run commands from here)
├── HackathonHollandseLuchten/     # hackathon repo, provides data/
│   └── data/
│       ├── reference_measurements.parquet
│       ├── reference_station_metadata.csv
│       └── knmi_weather_data.parquet        (not used yet)
└── Analyse-Together/              # R code, sourced at runtime (GPL-3, not copied)
    └── funs/data_to_tool_fun.R
```

```
cd <parent>
git clone git@github.com:rivm-syso/Analyse-Together.git
git clone git@github.com:provincieNH/HackathonHollandseLuchten.git
git clone git@github.com:markkrijgsman/hollandseluchten.git
```

Sensor data (`data_sensors.parquet`) is published on Zenodo on the day of the hackathon. It is optional: without it
the API uses official stations only. Download it anywhere and point `HL_SENSOR_PARQUET` at it.

If your layout differs, override the paths with the environment variables below.

## Setup

Requires Python 3.11+ and R 4.x.

```
brew install r                                          # or another R install
Rscript -e 'install.packages(c("dplyr", "jsonlite"))'

cd hollandseluchten/backend
python3 -m venv .venv
.venv/bin/pip install -e ".[chat,dev]"   # dependencies are declared in pyproject.toml
```

## Run and test

```
.venv/bin/uvicorn app.main:app          # http://localhost:8000/docs for the interactive docs
.venv/bin/pytest            # ~12 s
.venv/bin/ruff check app tests
```

Tests run on synthetic data written to a temp folder, so they need neither the hackathon repo nor the sensor file.
Tests that run the real R functions are skipped when `Rscript` or the Analyse-Together checkout is missing.
`tests/test_real_data.py` (marker `real_data`) smoke-tests the real hackathon data and is skipped when `HL_DATA_DIR` is missing.
The live OpenAI test (marker `live`) needs `OPENAI_API_KEY`.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HL_DATA_DIR` | `../../HackathonHollandseLuchten/data` | folder with the reference parquet/csv |
| `HL_ANALYSE_TOGETHER_DIR` | `../../Analyse-Together` | checkout whose R functions are sourced |
| `HL_SENSOR_PARQUET` | unset | path to Zenodo `data_sensors.parquet` |
| `HL_RSCRIPT` | `Rscript` | R executable |
| `HL_GUIDELINES_FILE` | `config/guidelines.toml` | reference levels for `/pm25/compare` |
| `HL_CONSIDERATIONS_FILE` | `config/considerations.toml` | rules for the considerations |
| `HL_GEOCODER_URL` | PDOK Locatieserver | geocoder endpoint |
| `OPENAI_API_KEY` | unset | enables OpenAI for `/chat` |
| `HL_CHAT_MODEL` | `gpt-4o` | OpenAI model id |

Defaults are relative to `backend/`. A missing Analyse-Together checkout or R installation makes the API return 503.
