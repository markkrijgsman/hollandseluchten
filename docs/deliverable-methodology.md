# Methodological Choices & Considerations — LuchtZorg (Challenge 3)

## 1. Core Design Philosophy

Residents in Noord-Holland ask concrete, personal questions about their air quality (*"Hoe verhoudt het fijnstof in Zaandam zich tot de WHO-norm?"*, *"Is de lucht op doordeweekse dagen slechter dan in het weekend?"*). Existing expert portals such as the [Samen Analyseren Tool](https://analyseren.samenmeten.nl/) and [Luchtmeetnet](https://www.luchtmeetnet.nl/) expose powerful data, but require residents to make specialist methodological decisions: choosing between raw and calibrated streams, selecting station IDs, setting outlier cutoffs, handling missing hours, and interpreting sensor uncertainty.

**LuchtZorg** is an open-source **hackathon prototype** that bridges this gap through two design principles:
1. **Deterministic Separation of Duties**: Language models translate resident questions and explain outcomes in everyday language, while **never performing arithmetic, estimating, or recalling air-quality numbers**. Every number comes from deterministic, auditable tools backed by RIVM’s *Samen Analyseren* R functions.
2. **Epistemic Honesty by Construction**: Every analytical response carries (a) a typed, step-by-step **audit trail** (`audit`), (b) dynamic **considerations** (`considerations`) derived from what actually happened in that run, with explicit provenance (`origin`: `analyse-together`, `this-api`, or `config`), and (c) a deterministic **reproduction URL** (`reproduce`) that reruns the exact calculation. Because low-cost optical citizen sensors carry higher uncertainty than official monitors, all estimates are explicitly framed as **indicative community context** rather than medical advice or statutory legal compliance.

---

## 2. System & Conversational Architecture

### Dual Resident Entry Points
- **Address Check (`/`)**: One-click postcode/street lookup via the Dutch government’s **PDOK Locatieserver**, presenting an immediate plain-language verdict against WHO/EU guidelines with progressive-disclosure drawers for station maps, time-series charts, methodological considerations, and the full audit table.
- **Conversational Analyst (`/gesprek/` -> `POST /chat`)**: Multi-turn natural-language dialogue powered by a stateless LangChain/LangGraph tool-calling agent (`backend/app/chat/engine.py`, supporting OpenAI `gpt-4o` and Google `gemini-3.5-flash-lite` at `temperature=0`).

### Shared Tool Registry (REST = Chat)
All nine analytical tools in `backend/app/tools/registry.py` power **both** the public REST endpoints and the `/chat` LLM agent through the exact same execution path:

| Tool / Endpoint | Analytical Purpose | Key Methodological Guardrails |
|---|---|---|
| `GET /geocode` | Dutch place/address -> WGS84 coordinates (PDOK) | Flags `ambiguous_place` when multiple Dutch localities match (e.g., *Haarlem* vs. *Haarlem, Groningen*). |
| `GET /coverage` | Dataset date bounds & station counts | Distinguishes network-wide date union from local station availability. |
| `GET /stations` | Nearby sensors & official stations within `radius_km` | Used by `/chat` when a resident asks about *"now"*/*"today"* so the agent queries the latest available day rather than guessing. |
| `GET /pm25` | Single-day $1/d^2$ PM2.5 estimate ($\mu\text{g/m}^3$) + uncertainty | Returns both `sensors` and `reference` station breakdowns side-by-side. |
| `GET /pm25/timeseries` | Daily (max 366 d) or hourly (max 31 d) PM2.5 series | Summarizes long series (`> 31` points) for the LLM context window while sending all points + full audit to the client. |
| `GET /pm25/compare` | Compare period against `who`, `eu`, or `eu2030` norms | Flags `partial_year` (`< 300` days) on annual limits and `annual_within_uncertainty` / `daily_within_uncertainty` when intervals straddle a norm. |
| `GET /pm25/weekday` | Weekday (Mon–Fri) vs. Weekend (Sat–Sun) comparison | Computes group means, min/max, day counts, and weekend–weekday delta; warns on small sample sizes (`< 5` weekend days). |
| `GET /pm25/trend` | Linear OLS slope ($\mu\text{g/m}^3$/day) over a date range | Classifies `improving`, `worsening`, or `stable` ($|\text{slope}| < 0.05\text{ }\mu\text{g/m}^3$/day) and warns when `< 14` days are used. |
| `GET /pm25/events` | Peak/exceedance day detection above `threshold` (default $15\text{ }\mu\text{g/m}^3$) | Counts exceedance days, share of valid days, and ambiguous days whose uncertainty band crosses `threshold`. |

### Why Not RAG or Text-to-SQL?
We deliberately chose **strongly-typed Pydantic tool calling** over unconstrained Text-to-SQL or RAG over raw CSVs:
- Text-to-SQL allows an LLM to accidentally average raw (`pm25_raw`) and calibrated (`pm25_kal`) values, mix UTC with `UTC+1` timestamps, ignore the 18-hour daily completeness rule, or omit uncertainty bands.
- Constrained tool calling guarantees that **100% of resident answers pass through the validated R pipeline and considerations engine**, while malformed coordinates or date ranges are caught by Pydantic validators (`app/tools/schemas.py`) and returned to the agent for self-correction.

---

## 3. Direct Integration of RIVM’s *Samen Analyseren* R Functions

A central requirement of Challenge 3 is compatibility with RIVM’s open-source [*Samen Analyseren* (`Analyse-Together`)](https://github.com/rivm-syso/Analyse-Together) R codebase (licensed under GPL-3).

- **Runtime R Bridge (`backend/r/analysis.R` & `app/integrations/r_bridge.py`)**: Rather than re-implementing RIVM’s calibration and uncertainty logic in Python (which risks silent numerical divergence), the backend invokes `Rscript` and `source()`s `funs/data_to_tool_fun.R` directly from a clean `Analyse-Together` Git checkout.
- **Fail-Closed Guarantee**: If `Rscript` or the `Analyse-Together` checkout is absent on the server, analysis endpoints return HTTP `503` rather than substituting an unvalidated Python approximation (`test_missing_r_or_checkout_is_an_error_not_a_silent_substitute`).
- **Dynamic Parameter Introspection & Commit Provenance**: `r/analysis.R` reads default uncertainty parameters directly via R’s `formals(add_uncertainty_sensor_percent)` and logs the exact `analyse_together_commit` SHA in every response’s `versions` audit step.

### Exact *Samen Analyseren* Steps Executed per Query
1. **Calibration Unification (`add_ref_kal`)**: Official Luchtmeetnet (`NL*`) hourly `pm25` measurements are promoted to `pm25_kal` (since reference monitors are certified instruments), and the dataset is filtered strictly to `parameter == "pm25_kal"`. Citizen sensor rows without a valid RIVM-calibrated `pm25_kal` value are **never** backfilled with `pm25_raw`.
2. **Outlier Cut-Off (`value < 100.0` $\mu\text{g/m}^3$)**: Identical to `communication_module.R` in *Samen Analyseren*, hourly values $\ge 100\text{ }\mu\text{g/m}^3$ are removed as likely optical sensor malfunctions (e.g., spiderwebs, fog/condensation spikes, hardware glitches). Both `hourly_values_in` and `outliers_removed` are recorded in the `r_functions` audit step.
3. **Sensor Measurement Uncertainty (`add_uncertainty_sensor_percent`)**: Each calibrated citizen sensor hour receives a standard uncertainty (`sd`) following RIVM’s *Boeren en Buren* defaults:
   $$u_{\text{sensor}}(x) = \max\!\left(0.20 \cdot x,\; 5.3\text{ }\mu\text{g/m}^3\right)$$
   Certified Luchtmeetnet reference stations receive $u_{\text{ref}} = 0\text{ }\mu\text{g/m}^3$ (consistent with `data_to_tool_fun.R`).

---

## 4. Spatial, Temporal & Uncertainty Aggregation Choices

Where *Samen Analyseren* operates on user-selected station groups, residents naturally ask about **an address or neighborhood**. LuchtZorg adds a transparent spatial-temporal aggregation layer (`backend/app/analysis/pipeline.py` and `weighting.py`), explicitly marked with `origin = "this-api"`:

### 4.1 Fixed `UTC+1` Day Definition & Time-Zone Alignment
- Official Luchtmeetnet files define days using a **fixed `UTC+1` offset year-round** (`00:00–24:00 UTC+1`, even during summer CEST), whereas Zenodo citizen sensor files store **naive UTC** timestamps (`timestamp_from`).
- `SensorRepository` (`app/data/repositories.py`) shifts sensor timestamps by `+01:00` before hourly/daily bucketing so sensor hours align identically with official reference hours without 1-hour daylight-saving shifts.
- Sensor rows with invalid GPS fixes (`0, 0` or coordinates outside the Netherlands bounding box `50.7–53.6°N, 3.3–7.3°E`) are filtered out on load, and each kit’s position is taken as its **median GPS coordinate** to guard against GPS jitter.

### 4.2 Daily Data Completeness ($\ge 18$ Valid Hours / Day)
- Following standard European air-quality aggregation practice (75% hourly capture = 18 of 24 hours), any station-day with `< 18` valid post-cutoff hours is excluded from daily means.
- Without this gate, a sensor that drops offline overnight or during humid morning rush hours produces a severely biased "daily average". Excluded station-periods are logged in `station_means` and surfaced via `sparse_stations_left_out`.

### 4.3 Inverse-Distance Squared ($1/d^2$) Weighting with a $0.5\text{ km}$ Floor
For all valid stations of a given `kind` within `radius_km` (default `5 km` neighbourhood-first in both the API/chat tools and the address dashboard, automatically expanding to `15 km` and `25 km` in sparser rural areas without nearby stations), weights are computed via Haversine distance $d_i$:
$$w_i = \frac{1}{\max(d_i,\; 0.5\text{ km})^2}, \qquad s_i = \frac{w_i}{\sum_{j} w_j}, \qquad \hat{y} = \sum_i s_i \bar{y}_i$$
- **Why $1/d^2$?** PM2.5 has a smooth regional background plus localized gradients near roads, waterways, or residential wood-burning pockets; inverse-squared distance prioritizes local stations while retaining neighborhood context.
- **Why the $0.5\text{ km}$ distance floor (`MIN_DISTANCE_KM = 0.5`)?** Directly operationalizes the citizen-science principle *"One sensor is no sensor"*. Without a floor, a single sensor 15 meters from the queried coordinate receives $> 99.9\%$ of the weight, allowing one faulty kit or a neighbor’s barbecue/chimney to dominate an entire neighborhood verdict even when three other sensors sit 400 meters away.

### 4.4 Calibrated Sensors First, Official Stations as Seamless Fallback
- Within each time period, `weighting.preferred()` selects the **calibrated Hollandse Luchten sensor estimate** whenever at least one sensor within `radius_km` has $\ge 18$ valid hours; otherwise it falls back to **official Luchtmeetnet reference stations**.
- Why? Citizen sensors provide hyper-local neighborhood density where official stations are kilometres away, while official Luchtmeetnet stations extend temporal coverage into 2026 (where the Zenodo sensor archive ends) and cover municipalities without active citizen kits. Whenever a multi-day series mixes both sources, the `mixed_basis` consideration explicitly warns the resident.

### 4.5 Conservative (Correlated) Uncertainty Propagation
When combining $K$ citizen sensors with weights $s_i$ and station uncertainties $\bar{u}_i$, LuchtZorg computes:
$$u_{\text{weighted}} = \sum_{i=1}^K s_i \bar{u}_i \quad \text{rather than} \quad \sqrt{\sum_{i=1}^K s_i^2 \bar{u}_i^2}$$
- **Justification**: Low-cost optical sensors (Sensirion SPS30 in SODAQ AIR kits) share systematic error modes—most notably hygroscopic swelling at high relative humidity and regional aerosol optical properties. Treating errors as independent ($\propto 1/\sqrt{K}$) would artificially shrink uncertainty in dense sensor clusters and create false confidence when comparing against strict WHO limits ($5\text{ }\mu\text{g/m}^3$ annual / $15\text{ }\mu\text{g/m}^3$ daily).

---

## 5. Transparent Considerations & Provenance Engine

Instead of appending generic boilerplate disclaimers to every page, `backend/config/considerations.toml` defines **26 declarative rules** evaluated against empirical run facts (`backend/app/analysis/facts.py`). Every triggered note includes:
- **`level`**: `info` (context), `caution` (material methodological caveat—always spoken aloud by the `/chat` assistant), or `warning`.
- **`origin`**:
  - `analyse-together` — behaviour or defaults inherited from RIVM’s tool (e.g., `outlier_cutoff = 100`, `sensor_uncertainty` 20% / min $5.3\text{ }\mu\text{g/m}^3$).
  - `this-api` — LuchtZorg’s own methodological thresholds, explicitly disclosed as engineering judgement rather than RIVM-validated rules (e.g., `many_outliers` $> 5\%$, `single_station`, `dominant_station` $\ge 70\%$ weight, `far_from_stations` $> 2\text{ km}$, `traffic_station_dominates` $\ge 50\%$ weight, `industry_station_dominates` $\ge 50\%$ weight, `mixed_basis`, `annual_within_uncertainty`, `daily_within_uncertainty`).
  - `config` — external guideline metadata in `config/guidelines.toml` (WHO 2021 annual $5\text{ }\mu\text{g/m}^3$ & 24h $15\text{ }\mu\text{g/m}^3$; EU Directive 2008/50/EC annual $25\text{ }\mu\text{g/m}^3$; EU Directive 2024/2881 2030 annual limit $10\text{ }\mu\text{g/m}^3$).
