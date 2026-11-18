# LuchtZorg — Frontend Setup & Developer Guide

The frontend is a **zero-build static web application** (vanilla HTML, CSS, and JavaScript). You do **not** need Node.js, npm, Webpack, or Vite to run or edit it locally—any HTTP server works immediately.

---

## 1. Quick Start (Run Frontend in 10 Seconds)

From the root of the `hollandseluchten` repository, start a static HTTP server in the `frontend/` directory:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory frontend
```

Then open in your browser:
- **Check my spot (Address Check)**: [http://localhost:8080/](http://localhost:8080/)
- **Ask a question (Chat)**: [http://localhost:8080/gesprek/](http://localhost:8080/gesprek/)
- **Pitch Deck (Presentation)**: [http://localhost:8080/presentation.html](http://localhost:8080/presentation.html)

> **Note:** Always serve `frontend/` over `http://localhost` rather than opening `.html` files via `file://` so browser `fetch()` requests and CORS work properly.

---

## 2. How Data & Backend Modes Work

The frontend automatically supports **live REST API** and **offline fallback** modes with zero configuration changes:

### Mode A: Live Backend REST API (`localhost:8000` locally or Cloud Run when hosted)
**Easiest local setup: Docker.** From the repository root, `docker compose up --build` starts the FastAPI + R backend (with `Analyse-Together`, Luchtmeetnet reference stations, and Zenodo citizen sensor data) on port `8000` and serves this frontend on `http://localhost:8080`. See the root [`README.md`](../README.md).

- On `localhost` / `127.0.0.1`, `js/api.js` connects to `http://localhost:8000` by default.
- On hosted domains (such as `https://luchtzorg.web.app`), `js/api.js` connects to the live Cloud Run backend (`https://luchtzorg-backend-103343530026.europe-west4.run.app`).
- **Custom API URL override**: Pass `?api=http://127.0.0.1:8000` in the browser URL to point to any backend host.
- On page load, `/` renders an instant initial card (`0 ms` first paint) and upgrades seamlessly with live `/stations`, `/pm25`, `/pm25/compare`, `/pm25/timeseries`, `/pm25/trend`, and `/pm25/events` results (`5 km` neighbourhood-first radius, auto-expanding to `15 km` → `25 km` in sparser rural areas).

### Mode B: Offline Fallback Mode (When Backend Is Unreachable)
If you run `frontend/` on `localhost:8080` without starting the backend:
- **Geocoding**: Calls the public Dutch government **PDOK Locatieserver API** (`api.pdok.nl`) directly from the browser.
- **Fallback Reference Data**: Uses `frontend/js/real-data.js` (embedded snapshot of Luchtmeetnet PM2.5 stations, `2025–2026`, `value < 100.0`, `>= 18 valid hours/day`) and clearly labels the result as `Offline reference dataset`.

---

## 3. Project Structure

```text
frontend/
├── index.html                   # Check my spot: compact location bar + above-the-fold verdict card, map & audit drawers
├── gesprek/index.html           # Ask a question: conversational analyst page (POST /chat)
├── over/index.html              # About LuchtZorg & prototype disclaimer
├── hollandse-luchten/index.html # About the Hollandse Luchten citizen-science network
├── tools/index.html             # Directory of related Dutch air-quality apps & open portals
├── contact/index.html           # Contact, GitHub & open API links
├── presentation.html            # Responsive 4-slide jury pitch deck (desktop + mobile + print-to-PDF)
├── app.css, styles.css          # LuchtZorg design system & mobile-first responsive styles
└── js/
    ├── nav.js                   # Shared AppBar, 2-tab switcher, native <dialog> drawer, NL/EN toggle & footer disclaimer
    ├── api.js                   # Backend client + typed `audit` & `considerations` translator
    ├── address.js               # Address lookup (PDOK), live backend bundle & offline fallback
    ├── address-page.js          # UI controller for index.html
    ├── chat.js                  # UI controller for /gesprek/
    ├── real-data.js             # Embedded snapshot of reference data (offline fallback)
    ├── mock-data.js, analysis.js, charts.js  # Helpers and SVG charts
    └── i18n.js                  # Auto-detected NL/EN bilingual state (persisted in localStorage)
```

---

## 4. Deploying to Firebase Hosting

The public live prototype is hosted on Firebase Hosting at:
- **Check my spot**: [https://luchtzorg.web.app/](https://luchtzorg.web.app/)
- **Ask a question**: [https://luchtzorg.web.app/gesprek/](https://luchtzorg.web.app/gesprek/)
- **Pitch Deck**: [https://luchtzorg.web.app/presentation.html](https://luchtzorg.web.app/presentation.html)

From the root of `hollandseluchten`, run:

```bash
npx -y firebase-tools@latest deploy --only hosting
```
