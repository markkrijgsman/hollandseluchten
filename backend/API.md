# PM2.5 API

`GET /pm25?lat=52.3676&lon=4.9041&date=2025-05-01[&radius_km=5][&cutoff=100][&min_hours=18]`

Returns the distance-weighted (1/d², floor 0.5 km) daily mean PM2.5 (µg/m³) of nearby stations, with
uncertainty, the per-station breakdown, limitations and an `audit` list of every step.
Uses Hollandse Luchten sensors (calibrated `pm25_kal`) when available, otherwise official Luchtmeetnet stations.
Calibration flag, uncertainty and outlier cut-off come from the Analyse-Together R functions (`r/analysis.R`).

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
.venv/bin/pip install fastapi uvicorn pandas pyarrow httpx pytest
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

Defaults are relative to `backend/`. A missing Analyse-Together checkout or R installation makes the API return 503.
