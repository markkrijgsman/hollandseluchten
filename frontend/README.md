# Hollandse Luchten — Frontend Setup & Developer Guide

The frontend is a **zero-build static web application** (vanilla HTML, CSS, and JavaScript). You do **not** need Node.js, npm, Webpack, or Vite to run or edit it on your laptop—any local HTTP server works immediately.

---

## 1. Quick Start (Run Frontend in 10 Seconds)

From the root of the `hollandseluchten` repository, start a static HTTP server in the `frontend/` directory:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

Then open either page in your browser:
- **Postcode & Adres Check (Primary Citizen Entry)**: [http://localhost:8080/adres.html](http://localhost:8080/adres.html)
- **Verdiepende Analyse & Chat (Deep-Dive Explorer)**: [http://localhost:8080/index.html](http://localhost:8080/index.html)

> **Note:** Always serve `frontend/` over `http://localhost` rather than opening `.html` files via `file://` so browser `fetch()` requests and CORS work properly.

---

## 2. How Data & Backend Modes Work

The frontend automatically supports **two modes** with zero configuration changes:

### Mode A: Full Local Backend REST API (`http://localhost:8000`)
When you also run the FastAPI backend locally on port `8000` (see [`../backend/API.md`](../backend/API.md)):

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000
```

- On page load, the frontend probes `http://localhost:8000/geocode` and `http://localhost:8000/stations`.
- When reachable, the status badge at the top of `adres.html` turns **green**:
  `Live Luchtmeetnet API (localhost:8000)`
- All address lookups, coverage checks, $1/d^2$ PM2.5 calculations, 365-day WHO/EU comparisons, time series, and `/chat` questions run directly against the local Python/R backend.
- **Custom API URL override**: Pass `?api=http://127.0.0.1:8000` in the browser URL to point to a different host or port.

### Mode B: Standalone Mode (No Backend Needed)
If `localhost:8000` is **not** running (or when hosted publicly on Firebase/GitHub Pages):
- **Geocoding**: Calls the public Dutch government **PDOK Locatieserver API** (`api.pdok.nl`) directly from the browser.
- **Air Quality Data**: Uses `frontend/js/real-data.js`—an embedded snapshot of the official **Hackathon Hollandse Luchten Parquet dataset** (67 Luchtmeetnet PM2.5 stations, 638 days from `2025-01-01` to `2026-09-30`, filtered with `value < 100.0` and `>= 18 valid hours/day`).
- **Calculations**: Runs the exact same Haversine distance + $1/d^2$ inverse-distance weighting, 365-day rolling mean, and WHO/EU exceedance counts in JavaScript.
- The status badge shows:
  `Echte Luchtmeetnet Parquet-dataset (67 stations · 2025–2026)`

---

## 3. Project Structure

```text
frontend/
├── adres.html          # Layer 1 Citizen Verdict Card + Layer 2 Progressive Disclosure Drawers
├── index.html          # Deep-Dive Sensor & Reference Explorer + Natural Language Chat
├── app.css             # Styling for adres.html (progressive disclosure, verdict cards, map, charts)
├── styles.css          # Styling for index.html (sensor explorer)
└── js/
    ├── address.js      # API client (localhost:8000), PDOK fallback, and 1/d² Parquet calculator
    ├── address-page.js # UI controller for adres.html (verdict card, Leaflet map, Canvas charts)
    ├── real-data.js    # Pre-computed daily PM2.5 series for 67 Luchtmeetnet stations (2025–2026)
    ├── mock-data.js    # Fallback station/sensor catalog for index.html (hydrates from real-data.js)
    ├── app.js          # UI controller for index.html + POST /chat integration
    ├── analysis.js     # Client-side statistical helpers for index.html
    ├── charts.js       # Canvas chart renderers for index.html
    ├── planner.js      # Query plan builder for index.html
    ├── intents.js      # Intent templates for index.html
    └── i18n.js         # NL/EN translations
```

---

## 4. Regenerating `js/real-data.js` (Optional)

`frontend/js/real-data.js` is already committed to Git, so you do **not** need to regenerate it to run the frontend.
If the Parquet dataset in `HackathonHollandseLuchten/data/` changes, you can regenerate `js/real-data.js` using Python + DuckDB:

```bash
cd backend
.venv/bin/python -c "
import duckdb, json, csv
# Queries reference_measurements.parquet (value < 100, count >= 18/day)
# and writes window.REAL_DATA to ../frontend/js/real-data.js
"
```

---

## 5. Deploying to Firebase Hosting

The public live demo is hosted on Firebase project `sample-bumps-firebase-ai-app` at:
- [https://hollandse-luchten-analyse.web.app/adres.html](https://hollandse-luchten-analyse.web.app/adres.html)
- [https://hollandse-luchten-analyse.web.app/index.html](https://hollandse-luchten-analyse.web.app/index.html)

### First-Time Setup (Once per Laptop)
Log in with the Google account that has **Editor** permissions on the Firebase project:

```bash
npx -y firebase-tools@latest login
```

### Deploy Frontend Changes
From the root of the `hollandseluchten` repository (where `firebase.json` and `.firebaserc` live), run:

```bash
npx -y firebase-tools@latest deploy --only hosting --project sample-bumps-firebase-ai-app
```
*(Or simply `npx -y firebase-tools@latest deploy --only hosting` after pulling `.firebaserc`.)*


