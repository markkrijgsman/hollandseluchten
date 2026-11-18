# Validation, Literature Comparison & Limitations — LuchtZorg (Challenge 3)

All quantitative benchmarks reported in this document are 100% reproducible from the official hackathon datasets using [`scripts/validate_approach.py`](../scripts/validate_approach.py) (raw output committed in [`docs/validation_metrics.json`](validation_metrics.json)):

```bash
python3 scripts/validate_approach.py --json docs/validation_metrics.json
```

---

## 1. Empirical Dataset & Data-Cleaning Audit

We audited the exact *Samen Analyseren* pre-processing rules (`value < 100 µg/m³` hourly cutoff and $\ge 18$ valid hours/day completeness) across the entire 2020–2026 Luchtmeetnet reference archive and the 2020–2025 Zenodo Hollandse Luchten sensor archive:

| Metric | Official Luchtmeetnet Stations (`reference_measurements.parquet`) | Hollandse Luchten Citizen Sensors (`data_sensors.parquet`, in NL) | Interpretation |
|---|---|---|---|
| **Active stations / kits** | **77** PM2.5 stations | **507** sensor kits | 6.6× denser spatial footprint in residential neighborhoods |
| **Date coverage** | `2020-01-01` – `2026-09-30` | `2020-01-01` – `2026-01-01` | 2026 queries automatically fall back to official stations (`reference_fallback`) |
| **Hourly PM2.5 rows** | **3,130,549** | **5,652,900** raw / **5,568,556** calibrated | **98.5%** calibration (`pm25_kal`) availability; uncalibrated 1.5% strictly dropped |
| **Hours $\ge 100\text{ }\mu\text{g/m}^3$ removed** | **605** (**0.0193%**) | **81,119** raw (**1.435%**) / **79,024** cal (**1.419%**) | Citizen sensors exhibit a **73× higher** extreme-spike rate than official monitors |
| **Share of $\ge 100$ hours on New Year’s (Dec 31–Jan 1)** | **86.1%** | — | In official data, $>100\text{ }\mu\text{g/m}^3$ is almost exclusively New Year’s fireworks |
| **Station-days excluded ($< 18$ valid hours)** | **1.31%** (of 132,340 days) | **6.10%** (of 240,611 kit-days) | Citizen kits suffer ~4.7× more partial-day dropouts (LoRaWAN/power), justifying the 18h gate |

---

## 2. Benchmark 1 — Spatial $1/d^2$ Interpolation (Leave-One-Out Cross-Validation)

To validate LuchtZorg’s spatial estimator ($\hat{y}$ via $1/d^2$ weighting with a $0.5\text{ km}$ floor), we ran **Leave-One-Out Cross-Validation (LOOCV)** across all official Luchtmeetnet PM2.5 stations from `2025-01-01` to `2026-09-30`. Each station’s true daily mean was held out and predicted solely from neighboring stations within $r = 5\text{ km}$ and $r = 15\text{ km}$:

| Subset / Stratum | Radius | Station-Days ($N$) | MAE ($\mu\text{g/m}^3$) | RMSE ($\mu\text{g/m}^3$) | Mean Bias ($\mu\text{g/m}^3$) | Pearson $r$ | $R^2$ |
|---|---|---:|---:|---:|---:|---:|---:|
| **All stations (overall)** | **5 km** (`59.6%` coverage) | 16,751 | **1.49** | **2.08** | −0.09 | **0.964** | **0.928** |
| **All stations (overall)** | **15 km** (`72.5%` coverage) | 20,383 | **1.46** | **2.02** | **+0.02** | **0.966** | **0.932** |
| — Background (`achtergrond`) | 15 km | 8,986 | 1.44 | 1.92 | **+0.45** | 0.971 | 0.939 |
| — Traffic (`verkeer`) | 15 km | 7,420 | 1.46 | 1.98 | **−0.45** | 0.968 | 0.932 |
| — Industrial (`industrie`) | 15 km | 3,977 | 1.49 | **2.32** | −0.08 | 0.957 | 0.915 |
| — Nearest station $\le 2\text{ km}$ | 15 km | 8,077 | 1.60 | 2.19 | −0.16 | 0.960 | 0.920 |
| — Nearest station $2\text{–}5\text{ km}$ | 15 km | 8,674 | 1.33 | 1.91 | +0.04 | 0.969 | 0.939 |
| — Nearest station $5\text{–}15\text{ km}$ | 15 km | 3,632 | 1.44 | 1.90 | +0.36 | 0.971 | 0.940 |

**Key Validation Takeaways:**
1. **High Regional Accuracy**: Because PM2.5 in the Netherlands has a strong regional background component, $1/d^2$ interpolation achieves **$1.46\text{ }\mu\text{g/m}^3$ MAE** and **$R^2 = 0.932$** across 20,383 station-days, while expanding `radius_km` from 5 km to 15 km increases coverage from **59.6% to 72.5%** without degrading MAE.
2. **Empirical Proof for Station-Type Consideration Rules**: Predicting a *traffic* station from surrounding stations under-estimates by **$-0.45\text{ }\mu\text{g/m}^3$**, whereas predicting a *background* residential location from nearby *traffic* monitors over-estimates by **$+0.45\text{ }\mu\text{g/m}^3$**, and *industrial* stations (e.g., IJmond) exhibit **21% higher RMSE ($2.32$ vs. $1.92\text{ }\mu\text{g/m}^3$)** due to directional plumes. This directly validates our `traffic_station_dominates` and `industry_station_dominates` rules in `config/considerations.toml`.

---

## 3. Benchmark 2 — Citizen Sensors vs. Co-Located Official Reference Stations

We matched **223 Hollandse Luchten sensor kits** located within **$\le 1.5\text{ km}$** of **14 official Luchtmeetnet PM2.5 stations** (including *Zaandam-Wagenschotpad*, *Beverwijk West-Creutzberglaan*, *IJmuiden-Kanaaldijk*, *Wijk aan Zee-Bosweg*, *Wijk aan Zee-Burgemeester Rothestraat*, *Velsen-Reijndersweg*, *Velsen-Staalstraat*, *Haarlem-Freddie Oversteegenstraat*, *Badhoevedorp-Sloterweg*, and four *Amsterdam* stations), yielding **85,883 paired kit-days** (2020–2025):

| Estimator / Regime | Paired Days ($N$) | MAE ($\mu\text{g/m}^3$) | RMSE ($\mu\text{g/m}^3$) | Mean Bias ($\mu\text{g/m}^3$) | Pearson $r$ | Uncertainty Band Coverage |
|---|---:|---:|---:|---:|---:|---:|
| **Single kit — Raw (`pm25_raw < 100`)** | 85,858 | 5.31 | 8.09 | +1.10 | 0.693 | — |
| **Single kit — RIVM Calibrated (`pm25_kal < 100`)** | 85,883 | **4.23** *(−20.3%)* | **7.31** *(−9.6%)* | **+1.01** | 0.656 | **77.3%** |
| **LuchtZorg Multi-Sensor $1/d^2$ ($\ge 3$ kits within $2.5\text{ km}$)** | 11,914 | **3.17** *(−40.3% vs raw)* | **4.97** *(−38.6% vs raw)* | +1.11 | **0.794** | **84.6%** |

### Stratification by Concentration & Relative Humidity (Confirming Literature)

| Physical Regime | Paired Days ($N$) | MAE ($\mu\text{g/m}^3$) | RMSE ($\mu\text{g/m}^3$) | Mean Bias ($\mu\text{g/m}^3$) | Pearson $r$ | Mean Relative Error |
|---|---:|---:|---:|---:|---:|---:|
| **Low concentration: Ref $< 10\text{ }\mu\text{g/m}^3$** (`pm25_kal`) | 55,912 | 3.03 | 5.78 | +0.96 | **0.268** | **55.4%** |
| **Elevated concentration: Ref $\ge 10\text{ }\mu\text{g/m}^3$** (`pm25_kal`) | 29,971 | 6.48 | 9.52 | +1.09 | **0.588** | **40.8%** |
| **High humidity: $\text{RH} > 80\%$ — Raw (`pm25_raw`)** | 15,073 | 6.56 | 9.63 | **+4.05** | 0.770 | — |
| **High humidity: $\text{RH} > 80\%$ — Calibrated (`pm25_kal`)** | 15,073 | **4.71** | **7.49** | **+2.58** | 0.774 | — |
| **Moderate humidity: $\text{RH} \le 80\%$ — Raw (`pm25_raw`)** | 70,785 | 5.04 | 7.72 | +0.48 | 0.674 | — |
| **Moderate humidity: $\text{RH} \le 80\%$ — Calibrated (`pm25_kal`)** | 70,785 | **4.12** | **7.20** | +0.66 | 0.627 | — |

**Key Validation Takeaways:**
1. **RIVM Calibration + Multi-Sensor $1/d^2$ Halves Error**: Using RIVM’s `pm25_kal` cuts single-sensor MAE by **20.3%** ($5.31 \to 4.23\text{ }\mu\text{g/m}^3$), and LuchtZorg’s $1/d^2$ multi-sensor pooling ($\ge 3$ kits) cuts MAE by another **25.1%** down to **$3.17\text{ }\mu\text{g/m}^3$** (RMSE $8.09 \to 4.97\text{ }\mu\text{g/m}^3$, $r = 0.794$), empirically proving the *"One sensor is no sensor"* rule.
2. **Well-Calibrated Uncertainty Intervals**: RIVM’s *Samen Analyseren* uncertainty band ($\pm \max(20\%, 5.3\text{ }\mu\text{g/m}^3)$) captures the true official reference value on **77.3%** of single-kit days and **84.6%** of multi-sensor $1/d^2$ days. If we had naively shrunk uncertainty by $1/\sqrt{K}$, coverage would have collapsed on high-humidity days, causing false WHO/EU exceedance verdicts.

---

## 4. Comparison with Research Literature & Domain Studies

Our empirical findings align closely with published Dutch citizen-science research:
- **GGD Amsterdam Co-Location Study of SODAQ AIR (Zaandam & Beverwijk, Aug 2024)**: GGD Amsterdam found that SODAQ AIR (Sensirion SPS30) sensors detect temporal peaks well ($r \approx 0.77\text{–}0.79$ during episodes) but lose correlation below $\sim 10\text{ }\mu\text{g/m}^3$ and overestimate under high humidity, making single sensors unsuitable for strict legal EU/WHO compliance checks. Our 85,883-day benchmark reproduces both effects quantitatively ($r = 0.268$ below $10\text{ }\mu\text{g/m}^3$; $+4.05\text{ }\mu\text{g/m}^3$ raw bias above $80\%$ RH) and directly motivates our `annual_within_uncertainty` and `daily_within_uncertainty` rules whenever a guideline limit falls inside $\hat{y} \pm u$.
- **RIVM Sensirion SPS30 Calibration & *Boeren en Buren* Studies (Wesseling et al., RIVM 2023–2024)**: Establishes the twin-parameter sensor uncertainty model ($\max(20\%, 5.3\text{ }\mu\text{g/m}^3)$ for PM2.5) implemented in `Analyse-Together` (`add_uncertainty_sensor_percent`) to account for low-concentration floor noise.
- **TNO & Waag — *Opgeruimd staat netjes* / Participatief Opschonen (Jul 2026)**: Highlights the tension between statistical outliers and genuine local pollution events (e.g., New Year’s fireworks, which account for **86.1%** of official hours $\ge 100\text{ }\mu\text{g/m}^3$ in our audit, vs. spiderwebs/condensation in citizen kits).
- **Note on Negative $R^2$ in Clean-Air Regimes**: As noted in the hackathon’s own methodology guide (`tips.md`), when true daily PM2.5 varies within a narrow $4\text{–}9\text{ }\mu\text{g/m}^3$ band ($\sigma_{\text{ref}} \approx 2.1\text{ }\mu\text{g/m}^3$), even a moderate optical sensor noise of $\sim 3\text{ }\mu\text{g/m}^3$ yields $R^2 < 0$ for individual kits—until multi-sensor $1/d^2$ pooling reduces variance and restores positive $R^2 = +0.354$ ($r = 0.794$).

---

## 5. Automated Test Verification

`backend/tests/` contains **7 automated pytest suites** validating deterministic correctness:
- `test_idw_and_calibration.py`: Verifies exact step-by-step $1/d^2$ math, $0.5\text{ km}$ distance floor clipping, $< 18\text{h}$ sparse-station exclusion, strict `pm25_kal`-only loading (never substituting `pm25_raw`), R `add_ref_kal` zero-uncertainty reference handling, R `add_uncertainty_sensor_percent` ($\max(20\%, 5.3)$), and fail-closed `503` errors when `Rscript` or `Analyse-Together` is missing.
- `test_considerations.py`: Tests all declarative `considerations.toml` triggers (`single_station`, `dominant_station`, `far_from_stations`, `traffic_station_dominates`, `mixed_basis`, `annual_within_uncertainty`, `ambiguous_place`).
- `test_chat.py` & `test_api.py`: Verifies multi-turn history reuse, clarifying questions when location is missing, latest-station-date lookup for *"now"* queries, LLM schema sanitization, and reproduction URL equivalence.

---

## 6. Known Issues & Limitations

We disclose six concrete limitations of our current approach:
1. **Isotropic $1/d^2$ Weighting Ignores Wind Direction & Plume Dispersion**: $1/d^2$ treats stations upwind and downwind identically. Near directional point sources (e.g., Tata Steel in IJmond or major highways A1/A9), wind-vector weighting and bivariate pollution roses using `knmi_weather_data.parquet` (`DD`, `FH`) are needed for source attribution.
2. **Static `< 100 µg/m³` Cutoff Trade-Offs**: Inherited from *Samen Analyseren*, the `< 100 µg/m³` rule clips genuine extreme smoke/firework hours (e.g., Jan 1 00:00–03:00) while failing to catch **sub-100 faulty readings**, such as **frozen/stuck sensors** (reporting an identical value for weeks) or moderate fog/humidity spikes ($35\text{–}95\text{ }\mu\text{g/m}^3$).
3. **Upstream Boundary Condition Discovered in `Analyse-Together` (`funs/data_to_tool_fun.R`, lines 117–126)**: During code review of RIVM’s `add_uncertainty_sensor_percent`, we identified that `dplyr::case_when` checks `sd < uc_min_pm25` and `sd > uc_min_pm25` using strict inequalities. When an hourly sensor value is *exactly* $26.5\text{ }\mu\text{g/m}^3$ ($20\% \times 26.5 = 5.3 = \text{uc\_min\_pm25}$), neither branch matches and R assigns `sd = 0`. Because we source `Analyse-Together` unmodified under GPL-3, we preserve upstream fidelity and document this edge case for RIVM maintainers.
4. **Residual High-Humidity Bias ($+2.58\text{ }\mu\text{g/m}^3$ for $\text{RH} > 80\%$)**: Even after RIVM calibration (`pm25_kal`), optical sensors retain a $+2.58\text{ }\mu\text{g/m}^3$ positive bias on foggy/damp days. Cross-checking KNMI humidity (`U > 80%`) as an additional `caution` consideration rule is a natural extension.
5. **PM2.5 Scope vs. Traffic & Wood-Smoke Questions**: PM2.5 is largely regional/secondary; it cannot isolate a single street’s 30 km/h speed-limit effect (where $\text{NO}_2$ Palmes tubes are appropriate) nor chemically distinguish domestic wood smoke (levoglucosan/black carbon) from background particulate matter, and `pm10_kal` is absent from the Zenodo sensor dataset.
6. **Sensor Metadata & Relocation Blind Spots**: Citizen sensor kits carry no station-type classification (`verkeer`/`industrie`/`achtergrond`, flagged via `sensor_type_unknown`), and taking a kit’s median GPS coordinate across a range can blur historical relocations if a kit was moved mid-year.

---

## 7. Disclosure of Generative AI & Tool Usage

In accordance with the Challenge 3 guidelines on transparent disclosure of generative AI:

1. **Runtime AI inside LuchtZorg (`POST /chat` only)**:
   - **Where used**: Translating natural-language resident questions (Dutch/English) into structured tool calls (`geocode`, `stations`, `pm25`, `pm25_compare`, `pm25_weekday`, `pm25_trend`, `pm25_events`, `pm25_timeseries`) and phrasing the tool’s structured JSON output and `caution`/`warning` considerations in accessible everyday language (`temperature=0`, via OpenAI `gpt-4o` or Google `gemini-3.5-flash-lite`).
   - **Where NOT used**: The LLM never performs arithmetic, data filtering, outlier removal, calibration, spatial interpolation, or norm comparison. The Address Check interface (`/`) and all `GET` REST endpoints run **100% deterministically with zero LLM involvement**.
2. **Development-Time AI Coding Assistants**:
   - **Where used**: AI coding assistants (Claude Code / Google Antigravity) were used during the hackathon to accelerate FastAPI boilerplate, vanilla HTML/CSS/SVG frontend UI and pitch-deck layout, Docker/Cloud Run configuration, and documentation formatting.
   - **Human design & verification**: Problem framing, architectural separation between LLM tool-calling and deterministic R execution, direct GPL-3 runtime sourcing of RIVM’s `Analyse-Together` R functions, the $1/d^2$ ($0.5\text{ km}$ floor) weighting and conservative correlated-uncertainty formulation, the 26 declarative consideration rules, the 7 automated `pytest` suites, and the quantitative Leave-One-Out / co-location validation benchmarks against Luchtmeetnet stations were designed, audited, and empirically verified by the team.
