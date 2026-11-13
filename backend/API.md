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
  tools/           schemas.py (request models), registry.py (tools shared by REST and chat)
  chat/            engine.py (loop), llm.py (Claude / stub), prompt.py, fake_llm.py
r/analysis.R       glue that sources Analyse-Together and applies its functions
config/            guidelines.toml
```

## Chat

`POST /chat` returns `answer`, `clarifying_question`, `interpretation` (every tool call made), `results` (full
envelopes with audit), `suggestions`, `llm` and `history`. It is stateless: send `history` back for follow-ups.
The model only picks tools and words the answer; all numbers come from the tools.

* With `ANTHROPIC_API_KEY` set it uses Claude (`HL_CHAT_MODEL`, default `claude-sonnet-5-5`).
* Without a key a **rule-based stub** answers (`llm` says so). It handles a place or `lat, lon` plus a date, a year or
  nothing; it is not a language model. Force it with `HL_LLM=fake`, or force Claude with `HL_LLM=anthropic`.

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
.venv/bin/pip install fastapi uvicorn pandas pyarrow httpx anthropic pytest
```

## Run and test

```
.venv/bin/uvicorn app.main:app          # http://localhost:8000/docs for the interactive docs
.venv/bin/pytest
```

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `HL_DATA_DIR` | `../../HackathonHollandseLuchten/data` | folder with the reference parquet/csv |
| `HL_ANALYSE_TOGETHER_DIR` | `../../Analyse-Together` | checkout whose R functions are sourced |
| `HL_SENSOR_PARQUET` | unset | path to Zenodo `data_sensors.parquet` |
| `HL_RSCRIPT` | `Rscript` | R executable |
| `HL_GUIDELINES_FILE` | `config/guidelines.toml` | reference levels for `/pm25/compare` |
| `HL_GEOCODER_URL` | PDOK Locatieserver | geocoder endpoint |
| `ANTHROPIC_API_KEY` | unset | enables Claude for `/chat` |
| `HL_LLM` / `HL_CHAT_MODEL` | auto / `claude-sonnet-5-5` | `fake` or `anthropic`; model id |

Defaults are relative to `backend/`. A missing Analyse-Together checkout or R installation makes the API return 503.
