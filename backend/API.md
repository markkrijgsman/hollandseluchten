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

Every analysis response contains `limitations`, an `audit` list of steps, the resolved `request` and a `reproduce`
URL that reruns it. Sensors (calibrated `pm25_kal`) are used when available, otherwise official Luchtmeetnet stations.
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
                   compare.py, catalog.py, limitations.py, versions.py, audit.py,
                   periods.py, constants.py, errors.py, geo.py, guidelines.py (config/guidelines.toml)
  data/            repositories.py (Luchtmeetnet and Hollandse Luchten parquet access)
  integrations/    r_bridge.py (Rscript + r/analysis.R), pdok.py (geocoder)
  analysis/models.py  typed responses (the Swagger response schemas)
  tools/           schemas.py (request models), responses.py, registry.py (tools shared by REST and chat)
  chat/            engine.py (agent run), tools.py (endpoints as LangChain tools), models.py, prompt.py, fake_llm.py
r/analysis.R       glue that sources Analyse-Together and applies its functions
config/            guidelines.toml
```

## Chat

`POST /chat` returns `answer`, `clarifying_question`, `interpretation` (every tool call made), `results` (full
envelopes with audit), `suggestions`, `llm` and `history`. It is stateless: send `history` back for follow-ups.
The model only picks tools and words the answer; all numbers come from the tools.

It is a LangChain agent (`langchain.agents.create_agent`, on LangGraph) whose tools are the endpoints above
(`chat/tools.py`). The tool result goes to the model without audit; the full result goes to the client.

* With `OPENAI_API_KEY` set it uses OpenAI (`HL_CHAT_MODEL`, default `gpt-4o`).
* Without a key a **rule-based stub** answers (`llm` says so). It handles a place or `lat, lon` plus a date, a year or
  nothing; it is not a language model. Force it with `HL_LLM=fake`, or force OpenAI with `HL_LLM=openai`.
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
| `HL_GEOCODER_URL` | PDOK Locatieserver | geocoder endpoint |
| `OPENAI_API_KEY` | unset | enables OpenAI for `/chat` |
| `HL_LLM` / `HL_CHAT_MODEL` | auto / `gpt-4o` | `fake` or `openai`; model id |

Defaults are relative to `backend/`. A missing Analyse-Together checkout or R installation makes the API return 503.
