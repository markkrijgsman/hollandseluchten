# LuchtZorg — Hollandse Luchten Hackathon (Challenge 3)

> **For people who care for their air** — Helping residents of Noord-Holland explore, question, and understand local PM2.5 air quality in everyday language, backed by RIVM’s validated *Samen Analyseren* R functions and a complete, reproducible audit trail.

- **Live Web App (Address Check)**: [https://luchtzorg.web.app/](https://luchtzorg.web.app/)
- **Live Conversational Analyst (`/gesprek/`)**: [https://luchtzorg.web.app/gesprek/](https://luchtzorg.web.app/gesprek/)
- **Live Pitch Deck**: [https://luchtzorg.web.app/presentation.html](https://luchtzorg.web.app/presentation.html)
- **Live Backend OpenAPI / Swagger Docs**: [https://luchtzorg-backend-103343530026.europe-west4.run.app/docs](https://luchtzorg-backend-103343530026.europe-west4.run.app/docs)

---

## Hackathon Deliverables Index

| Deliverable | Location in Repository |
|---|---|
| **1. Self-contained local setup & codebase** | This `README.md`, [`docker-compose.yml`](docker-compose.yml), [`setup.sh`](setup.sh), [`backend/`](backend/), [`frontend/`](frontend/) |
| **2. Jury pitch presentation (max 5 min)** | [`docs/LuchtZorg_Presentation.pdf`](docs/LuchtZorg_Presentation.pdf) (offline PDF) & [`frontend/presentation.html`](frontend/presentation.html) (interactive deck) |
| **3. Concrete end-to-end Challenge 3 example** | [`docs/deliverable-example-end-to-end.pdf`](docs/deliverable-example-end-to-end.pdf) & [`.md`](docs/deliverable-example-end-to-end.md) — real resident question + follow-up, audit trail, *Samen Analyseren* R calls & reproduction URLs |
| **4. Methodological choices & considerations** | [`docs/deliverable-methodology.pdf`](docs/deliverable-methodology.pdf) & [`.md`](docs/deliverable-methodology.md) (rules config: [`backend/config/considerations.toml`](backend/config/considerations.toml)) |
| **5. Validation, reference comparison & AI disclosure** | [`docs/deliverable-validation.pdf`](docs/deliverable-validation.pdf) & [`.md`](docs/deliverable-validation.md) (reproducible script: [`scripts/validate_approach.py`](scripts/validate_approach.py), metrics: [`docs/validation_metrics.json`](docs/validation_metrics.json)) |

---

## Quick Start: Run Locally From Scratch

You can run the complete stack from scratch either **with Docker** (recommended — nothing else to install) or **natively** (Python 3.11+ and R 4.x).

### Option A: One-Command Docker Setup (Recommended)

Requires only **Docker Desktop** (or Docker Engine + Compose). No local R, Python, or manual data downloads are needed.

```bash
git clone https://github.com/markkrijgsman/hollandseluchten.git
cd hollandseluchten

# Optional: enable the /chat conversational assistant with an OpenAI or Google Gemini API key
cp .env.example .env
# Edit .env and set OPENAI_API_KEY=... or GEMINI_API_KEY=...

docker compose up --build
```

What happens on first startup:
1. `data-init` clones the official `HackathonHollandseLuchten` reference dataset (`reference_measurements.parquet`, 77 Luchtmeetnet stations, 2020–Sep 2026) and downloads + MD5-verifies the Zenodo `data_sensors.parquet` citizen sensor archive (507 kits, ~80 MB) into a persistent Docker volume (`hl-data`).
2. `backend` builds Python 3.11 + R (`dplyr`, `jsonlite`) + a runtime checkout of RIVM’s [`Analyse-Together`](https://github.com/rivm-syso/Analyse-Together) repository and serves the REST + `/chat` API on **http://localhost:8000** (Swagger UI at **http://localhost:8000/docs**).
3. `frontend` serves the zero-build web application on **http://localhost:8080**.

Open in your browser:
- **Address Check & Audit Drawer**: [http://localhost:8080/](http://localhost:8080/)
- **Conversational AI Analyst**: [http://localhost:8080/gesprek/](http://localhost:8080/gesprek/)
- **Pitch Deck**: [http://localhost:8080/presentation.html](http://localhost:8080/presentation.html)
- **Interactive API Docs (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

> **Without an LLM API key:** All deterministic endpoints (`/geocode`, `/coverage`, `/guidelines`, `/stations`, `/pm25`, `/pm25/timeseries`, `/pm25/compare`, `/pm25/weekday`, `/pm25/trend`, `/pm25/events`) and the entire Address Check UI work 100% without any API key; only `POST /chat` requires `OPENAI_API_KEY` or `GEMINI_API_KEY` (returning HTTP `503` otherwise).

Stop containers with `docker compose down` (add `-v` to also remove the downloaded data volume).

---

### Option B: Native Setup (Without Docker)

Requires `git`, **Python 3.11+**, and **R 4.x** (`brew install r` on macOS; `sudo apt install r-base` on Ubuntu/Debian).

```bash
git clone https://github.com/markkrijgsman/hollandseluchten.git
cd hollandseluchten

# Clones Analyse-Together & HackathonHollandseLuchten as sibling directories,
# installs R packages (dplyr, jsonlite) + backend/.venv, downloads & verifies Zenodo sensor data,
# and runs an end-to-end R bridge smoke test:
./setup.sh            # pass --no-sensors to skip the 80 MB Zenodo sensor archive
```

Then in two terminals:

```bash
# Terminal 1 — FastAPI + R Backend (port 8000)
cd backend
export OPENAI_API_KEY=...   # or export GEMINI_API_KEY=... (only needed for POST /chat)
.venv/bin/uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2 — Zero-build Static Frontend (port 8080)
python3 -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

### Run Automated Tests & Reproducible Validation

```bash
# Unit & integration test suite (~12 s; uses synthetic + R bridge fixtures)
cd backend && .venv/bin/pytest

# Reproducible LOOCV + co-located sensor vs. reference validation on the real Parquet datasets
cd .. && backend/.venv/bin/python scripts/validate_approach.py
```

---

## Architecture Overview

```text
hollandseluchten/
├── frontend/                   # Zero-build vanilla HTML/CSS/JS progressive web client
│   ├── index.html              # Instant address health verdict + progressive-disclosure audit drawers
│   ├── gesprek/index.html      # Multi-turn Dutch/English conversational interface (POST /chat)
│   ├── over/ · hollandse-luchten/ · tools/ · contact/  # About, ecosystem apps directory & contact pages
│   ├── presentation.html       # Responsive 4-slide jury pitch deck (desktop + mobile swipe)
│   └── js/                     # nav.js, api.js, address.js, chat.js, charts.js, i18n.js
├── backend/                    # FastAPI + LangGraph agent + R bridge (see backend/API.md)
│   ├── app/
│   │   ├── main.py             # Deterministic REST endpoints + POST /chat
│   │   ├── analysis/           # Shared pipeline: station selection -> R bridge -> 1/d² weighting -> considerations
│   │   ├── chat/               # Stateless tool-calling LLM agent (never computes numbers itself)
│   │   ├── data/               # Fixed UTC+1 Parquet/CSV repositories (Luchtmeetnet + Zenodo HoLu kits)
│   │   ├── integrations/       # r_bridge.py (Rscript subprocess) & pdok.py (PDOK Locatieserver geocoder)
│   │   └── tools/              # Single registry & Pydantic schemas shared by REST and LLM tool-calling
│   ├── r/analysis.R            # Sources RIVM's Analyse-Together (add_ref_kal, cutoff < 100, sensor uncertainty)
│   ├── config/                 # Declarative guidelines.toml (WHO/EU) & considerations.toml (26 provenance rules)
│   └── tests/                  # 7 pytest suites covering IDW, calibration, considerations, API & chat
├── scripts/
│   ├── fetch-sensors.sh        # Downloads & MD5-verifies Zenodo data_sensors.parquet (record 23762846)
│   └── validate_approach.py    # Reproducible LOOCV & co-located sensor-vs-reference validation benchmark
└── docs/                       # Hackathon deliverables, presentation PDF & validation metrics
```

Key architectural guarantees (detailed in [`docs/deliverable-methodology.md`](docs/deliverable-methodology.md)):
- **Zero Numerical Hallucinations**: In `POST /chat`, the LLM only selects typed tools and summarizes tool outputs; every PM2.5 concentration, exceedance count, trend slope, and uncertainty bound is computed deterministically by the backend and returned alongside `interpretation` (every tool call) and `reproduce` URLs.
- **Validated RIVM Science at Runtime**: `backend/r/analysis.R` sources `funs/data_to_tool_fun.R` directly from a sibling checkout of RIVM’s GPL-3 [`Analyse-Together`](https://github.com/rivm-syso/Analyse-Together) repository (`add_ref_kal`, `< 100 µg/m³` outlier cut-off, `add_uncertainty_sensor_percent` with $\max(20\%, 5.3\text{ }\mu\text{g/m}^3)$) and logs the exact Git commit in every response’s `versions` audit step.
- **Explicit Provenance (`origin`)**: Every dynamic caveat in `considerations` states whether the underlying rule comes from `analyse-together`, `this-api` (our own spatial/completeness thresholds), or `config` (WHO/EU norm definitions).

---

## Disclosure of Generative AI & Tool Usage

In accordance with the Challenge 3 guidelines on transparent disclosure of generative AI:

1. **Runtime AI inside LuchtZorg (`POST /chat` only)**:
   - **Where used**: Translating natural-language resident questions (Dutch/English) into structured tool calls (`geocode`, `stations`, `pm25`, `pm25_compare`, `pm25_weekday`, `pm25_trend`, `pm25_events`, `pm25_timeseries`) and phrasing the tool’s structured JSON output and `caution`/`warning` considerations in accessible language (`temperature=0`, via OpenAI `gpt-4o` or Google `gemini-3.5-flash-lite` / `gemini-3.8-flash`).
   - **Where NOT used**: The LLM never performs arithmetic, data filtering, outlier removal, calibration, spatial interpolation, or norm comparison. The Address Check interface (`/` and `/adres.html`) and all `GET` REST endpoints run **100% deterministically with zero LLM involvement**.
2. **Development-Time AI Coding Assistants**:
   - **Where used**: AI coding assistants (Claude Code / Google Antigravity) were used during the hackathon to accelerate FastAPI boilerplate, vanilla HTML/CSS/Canvas frontend UI and pitch-deck layout, Docker/Cloud Run configuration, and markdown documentation structuring.
   - **Human design & verification**: Problem framing, architectural separation between LLM tool-calling and deterministic R execution, direct GPL-3 runtime sourcing of RIVM’s `Analyse-Together` R functions, the $1/d^2$ ($0.5\text{ km}$ floor) weighting and conservative correlated-uncertainty formulation, the 26 declarative consideration rules, the 7 automated `pytest` suites, and the quantitative Leave-One-Out / co-location validation benchmarks against Luchtmeetnet stations were designed, audited, and empirically verified by the team.

---

## External Data & Domain References

- **Official Reference Network**: [Luchtmeetnet Open Data (RIVM / GGD Amsterdam / Provincie Noord-Holland)](https://data.rivm.nl/data/luchtmeetnet/)
- **Citizen Sensor Archive**: [Five years of Hollandse Luchten sensor data (Zenodo record 23762846)](https://zenodo.org/records/23762846) & [Samen Meten Portal](https://www.samenmeten.nl/)
- **Validated Analysis Codebase**: [RIVM `Analyse-Together` (*Samen Analyseren Tool*, GPL-3)](https://github.com/rivm-syso/Analyse-Together)
- **Geocoding**: [Kadaster / PDOK Locatieserver API](https://api.pdok.nl/)
