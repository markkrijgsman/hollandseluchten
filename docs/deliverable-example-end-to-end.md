# End-to-End Real-Life Example & Audit Trail — LuchtZorg (Challenge 3)

This document demonstrates **LuchtZorg** handling a genuine Noord-Holland resident inquiry end-to-end—including autonomous place disambiguation, multi-turn follow-up refinement, plain-language resident explanation, provenance-tagged considerations, and the complete *Samen Analyseren* R audit trail.

- **Full verbatim JSON response (Turn 1 — WHO comparison)**: [`docs/examples/zaanse_schans_chat_turn1.json`](examples/zaanse_schans_chat_turn1.json)
- **Full verbatim JSON response (Turn 2 — Weekday vs. Weekend follow-up)**: [`docs/examples/zaanse_schans_chat_turn2.json`](examples/zaanse_schans_chat_turn2.json)

---

## 1. Real-Life Resident Scenario (Hackathon Dataset Question #4757)

In [`HackathonHollandseLuchten/data/resident_questions.csv`](https://github.com/provincieNH/HackathonHollandseLuchten) (**ID `4757`**, Zaanse Schans, `52.4726°N, 4.8204°E`), a resident asked:

> *"Hoe verhouden de fijnstof of NO2-niveau’s rondom de Zaanse Schans zich tot de normen? Ik ben benieuwd of uitbreiding van de bezoekersaantallen invloed heeft op deze niveau’s."*

Historically, answering this single question required data analysts manually downloading CSV files for nearby Hollandse Luchten sensors (`378` and `415`), cross-checking RIVM GCN maps (`~8.1 µg/m³` in 2025), and writing a custom workshop report. Below is the exact live execution of this inquiry—plus a weekend-visitor follow-up—through LuchtZorg’s `POST /chat` pipeline (`/gesprek/`).

---

## 2. Turn 1: Natural-Language Question → WHO Guideline Comparison

### Resident Input
```json
POST /chat
{
  "message": "Hoe verhouden de fijnstofniveaus (PM2.5) rond de Zaanse Schans in 2025 zich tot de WHO-norm?",
  "history": []
}
```

### Autonomous Multi-Step Tool Trajectory (`interpretation`)
Because the LLM (`gemini-3.5-flash-lite`, `temperature=0`) is forbidden from guessing coordinates or numbers, it executed a 5-step self-correcting tool sequence:

| Call | Tool | Arguments | Outcome & Self-Correction |
|---:|---|---|---|
| **1** | `geocode` | `{"q": "Zaanse Schans"}` | PDOK returns 5 Dutch matches. Candidate #1 is a street named *Zaanse Schans* in **Capelle aan den IJssel** (`51.9512, 4.5905`); Candidate #2 is **Zaanse Schans Zaanstad** (`52.4759, 4.8248`). Flags `ambiguous_place`. |
| **2** | `pm25_compare` | `{"lat": 51.9512, "lon": 4.5905, "from": "2025-01-01", "to": "2025-12-31", "against": "who"}` | Returns `Error 404: No PM2.5 data within 5.0 km` (South Holland street outside sensor coverage). |
| **3** | `stations` | `{"lat": 51.9512, "lon": 4.5905}` | Confirms `0` stations within 5 km of Capelle aan den IJssel; agent inspects alternative PDOK match *Zaanse Schans Zaanstad*. |
| **4** | `geocode` | `{"q": "Zaanse Schans Zaanstad"}` | Resolves exact Noord-Holland heritage area (`52.47590499, 4.8248332`). |
| **5** | `pm25_compare` | `{"lat": 52.47590499, "lon": 4.8248332, "from": "2025-01-01", "to": "2025-12-31", "against": "who"}` | Computes 365-day $1/d^2$ series via RIVM’s *Samen Analyseren* R functions (`reproduce`: `/pm25/compare?lat=52.47590499&lon=4.8248332&radius_km=5.0&from=2025-01-01&to=2025-12-31&min_hours=18&cutoff=100.0&against=who`). |

### Explanation Shown to the Resident (`answer`)

> Bij het opzoeken van de Zaanse Schans heb ik de locatie **Zaanse Schans Zaanstad** gebruikt (er waren ook andere plaatsen met deze naam, waaronder een weg in Capelle aan den IJssel).
>
> In **2025** was de gemiddelde fijnstofconcentratie (PM2.5) rond de Zaanse Schans **8.6 µg/m³** (gebaseerd op 365 dagen met data, afkomstig van een combinatie van sensoren en officiële stations). De WHO-advieswaarde voor het jaargemiddelde is **5 µg/m³**, en voor de 24-uursgemiddelden is dat **15 µg/m³** (deze normen komen uit de WHO Global Air Quality Guidelines 2021).
>
> **Belangrijke kanttekeningen bij deze resultaten:**
> * **Onzekerheid:** De onzekerheid is gemiddeld 106% van de waarde. Zowel het jaargemiddelde als de daggemiddelden vallen binnen deze onzekerheidsmarge ten opzichte van de WHO-normen, waardoor het niet met zekerheid te zeggen is of de normen officieel zijn overschreden.
> * **Basis en stations:** De berekening gebruikt een schatting op basis van nabijgelegen meetpunten; 1 van de 365 periodes steunde op een enkel station (waardoor lokale afwijkingen niet worden uitgemiddeld), en de basis veranderde gedurende het jaar.
> * **Sensoren:** De gebruikte sensor kits hebben geen bekende typering (verkeer, industrie of achtergrond), en de onzekerheid van sensoren is een vaste schatting (20%, minimaal 5.3 µg/m³).

*(Note: LuchtZorg’s automated 2025 estimate of **`8.6 ± 5.45 µg/m³`**—with **50 of 365 days** above the 15 µg/m³ WHO daily guideline—aligns remarkably closely with the manual RIVM/GCN expert benchmark of `8.1 µg/m³` and sensors `378`/`415` (`5.4–10.35 µg/m³`) recorded in `resident_questions.csv` #4757!)*

---

## 3. Complete Audit Trail of Data, Choices & *Samen Analyseren* R Functions

Every analysis result returned to the frontend includes a typed 8-step `audit` array and a dynamic `considerations` list:

### 3.1 Step-by-Step `audit` Trace (Verbatim JSON from `results[-1].audit`)

```json
[
  {
    "step": 1,
    "action": "request",
    "code": "request",
    "lat": 52.47590499,
    "lon": 4.8248332,
    "start": "2025-01-01",
    "end": "2025-12-31",
    "resolution": "day",
    "radius_km": 5.0,
    "outlier_cutoff": 100.0,
    "min_hours_per_station": 18,
    "day_definition": "00:00-24:00 fixed UTC+1 (as in the Luchtmeetnet files)"
  },
  {
    "step": 2,
    "action": "select reference stations",
    "code": "select_stations",
    "kind": "reference",
    "source": "Luchtmeetnet",
    "stations": ["NL49701"],
    "station_types": {"NL49701": "achtergrond"},
    "note": "official stations; PM2.5 hourly values"
  },
  {
    "step": 3,
    "action": "select Hollandse Luchten sensors",
    "code": "select_stations",
    "kind": "sensor",
    "source": "Hollandse Luchten",
    "stations": [
      "HLL_hl_device_108", "HLL_hl_device_232", "HLL_hl_device_238", "HLL_hl_device_256",
      "HLL_hl_device_263", "HLL_hl_device_273", "HLL_hl_device_323", "HLL_hl_device_325",
      "HLL_hl_device_332", "HLL_hl_device_348", "HLL_hl_device_349", "HLL_hl_device_351",
      "HLL_hl_device_356", "HLL_hl_device_358", "HLL_hl_device_360", "HLL_hl_device_365",
      "HLL_hl_device_367", "HLL_hl_device_369", "HLL_hl_device_375", "HLL_hl_device_378",
      "HLL_hl_device_385", "HLL_hl_device_390", "HLL_hl_device_401", "HLL_hl_device_403",
      "HLL_hl_device_405", "HLL_hl_device_409", "HLL_hl_device_413", "HLL_hl_device_415",
      "HLL_hl_device_445", "HLL_hl_device_496", "HLL_hl_device_503", "HLL_hl_device_541"
    ],
    "note": "calibrated PM2.5 (pm25_kal), hourly mean"
  },
  {
    "step": 4,
    "action": "R: Analyse-Together functions",
    "code": "r_functions",
    "functions": [
      "add_ref_kal",
      "outlier cut-off (value < cutoff)",
      "add_uncertainty_sensor_percent"
    ],
    "parameters": {
      "outlier_cutoff": 100.0,
      "sensor_uncertainty_percent": 20.0,
      "sensor_uncertainty_min_ug_m3": 5.3
    },
    "hourly_values_in": 116634,
    "outliers_removed": 88
  },
  {
    "step": 5,
    "action": "daily mean per station",
    "code": "station_means",
    "station_periods_used": 4841,
    "station_periods_excluded_for_too_few_hours": 165
  },
  {
    "step": 6,
    "action": "distance-weighted mean per period",
    "code": "weighted_mean",
    "weights": "1/max(d, 0.5 km)^2",
    "periods": 365,
    "periods_from_sensors": 364
  },
  {
    "step": 7,
    "action": "compare with reference levels",
    "code": "compare",
    "against": "who",
    "levels": [
      {"id": "who_2021_24h", "limit": 15.0, "source": "WHO Global Air Quality Guidelines 2021", "verified": false},
      {"id": "who_2021_annual", "limit": 5.0, "source": "WHO Global Air Quality Guidelines 2021", "verified": false}
    ]
  },
  {
    "step": 8,
    "action": "versions",
    "code": "versions",
    "analyse_together_commit": "187769625d7073fcba248082d76a38dec10decac",
    "reference_data": {
      "file": "reference_measurements.parquet",
      "size_bytes": 40883038,
      "covers": {"from": "2020-01-01", "to": "2026-09-30"}
    },
    "sensor_data": {
      "file": "data_sensors.parquet",
      "size_bytes": 83888493,
      "covers": {"from": "2020-01-01", "to": "2026-01-01"}
    }
  }
]
```

Notice in **Step 3** that LuchtZorg automatically selected **`HLL_hl_device_378`** and **`HLL_hl_device_415`**—the exact two Zaanse Schans kits manually analyzed by RIVM/TNO experts—alongside 30 neighboring Zaanstad kits and official background station **`NL49701` (*Zaandam-Wagenschotpad*)**, passed **116,634 hourly measurements** through RIVM’s R functions (**Step 4**, removing **88** outliers $\ge 100\text{ }\mu\text{g/m}^3$), excluded **165** incomplete kit-days with $< 18$ hours (**Step 5**), and fell back to `NL49701` on the **1 day** of 2025 where no local sensor had $\ge 18$ valid hours (**Step 6**).

### 3.2 Triggered Methodological Considerations (`considerations`)

| Code | Level | Origin | Message Shown & Facts |
|---|---|---|---|
| `ambiguous_place` | `caution` | `this-api` | Discloses multiple PDOK matches (*Capelle aan den IJssel* vs. *Zaanse Schans Zaanstad*). |
| `annual_within_uncertainty` | `caution` | `this-api` | Period mean (`8.6 µg/m³`, uncertainty `5.45 µg/m³`) straddles WHO annual `5 µg/m³` (`[3.15, 14.05]`). |
| `daily_within_uncertainty` | `caution` | `this-api` | On **81 of 365 days**, the daily uncertainty interval contains the WHO 24h limit (`15 µg/m³`; 50 days nominally above, 26 strictly above at lower bound, 107 at upper bound). |
| `mixed_basis` | `caution` | `this-api` | **1 of 365 days** used official station `NL49701` because no sensor had $\ge 18$ valid hours (`364` sensor days + `1` reference day). |
| `single_station` | `caution` | `this-api` | At least one period rested on a single station (`NL49701` fallback day). |
| `high_relative_uncertainty` | `caution` | `this-api` | Sensor uncertainty (`min 5.3 µg/m³`) averages **106%** of low daily concentrations. |
| `sensor_uncertainty` | `info` | `analyse-together` | Fixed sensor uncertainty (`20%`, min `5.3 µg/m³`) is not reduced by averaging. |
| `outliers_removed` | `info` | `analyse-together` | **88 of 116,634** hourly values (`0.1%`) $\ge 100\text{ }\mu\text{g/m}^3$ removed as outliers. |
| `sparse_stations_left_out` | `info` | `this-api` | **165** station-days with fewer than `18` valid hours excluded. |
| `sensor_type_unknown` | `info` | `this-api` | Citizen sensor kits carry no station type (`traffic`/`industry`/`background`). |

---

## 4. Turn 2: Multi-Turn Resident Follow-Up (Weekday vs. Weekend Visitors)

To investigate whether weekend tourist crowds at the Zaanse Schans noticeably worsen PM2.5 compared to weekdays, the resident asks a natural follow-up—passing Turn 1’s `history` back to `POST /chat`:

### Resident Follow-Up Input
```json
POST /chat
{
  "message": "En was het fijnstof daar in 2025 op doordeweekse dagen hoger dan in het weekend?",
  "history": ["...Turn 1 messages..."]
}
```

### Tool Call & Audit Step 7 (`weekday_split`)
Without asking for the location again, the agent reuses `(52.47590499, 4.8248332)` from `history` and calls `pm25_weekday`:
- **Reproduction URL**: `/pm25/weekday?lat=52.47590499&lon=4.8248332&radius_km=5.0&from=2025-01-01&to=2025-12-31&min_hours=18&cutoff=100.0`
- **Audit Step 7 (`weekday_split`)**:
  ```json
  {
    "step": 7,
    "action": "weekday vs weekend split",
    "code": "weekday_split",
    "weekday_days": 261,
    "weekend_days": 104,
    "weekday_mean": 8.55,
    "weekend_mean": 8.71,
    "difference": 0.16
  }
  ```

### Explanation Shown to the Resident (`answer`)

> In **2025** was het fijnstofniveau (PM2.5) rond de Zaanse Schans op doordeweekse dagen gemiddeld **8.55 µg/m³** (gemeten over 261 dagen), en in het weekend gemiddeld **8.71 µg/m³** (gemeten over 104 dagen). Het verschil bedraagt **0.16 µg/m³**, wat betekent dat de niveaus in het weekend net iets hoger waren dan op doordeweekse dagen.
>
> **Belangrijke kanttekeningen bij deze resultaten:**
> * **Onzekerheid:** De onzekerheid is gemiddeld 106% van de waarde. Daardoor is het verschil tussen doordeweekse dagen en het weekend zo klein ten opzichte van de meetmarge dat er geen harde conclusie aan verbonden kan worden.

---

## 5. Single-Day Station Weighting Breakdown (`GET /pm25`)

Inspecting a single day (`2025-05-15`) at Zaanse Schans (`52.4726, 4.8204`) via `/pm25` illustrates how the $1/\max(d, 0.5\text{ km})^2$ weighting combines neighborhood sensors while exposing the official reference station side-by-side:

| Source Group | Station / Kit ID | Distance (`km`) | Weight Share | Valid Hours | Daily Mean (`µg/m³`) | Uncertainty (`µg/m³`) |
|---|---|---:|---:|---:|---:|---:|
| **Hollandse Luchten (primary)** | `HLL_hl_device_378` | 0.29 *(floored to 0.50)* | **0.330** | 24 | 7.13 | 5.30 |
| | `HLL_hl_device_415` | 0.65 | **0.195** | 24 | 7.38 | 5.30 |
| | `HLL_hl_device_232` | 0.81 | **0.125** | 24 | 6.07 | 5.30 |
| | `HLL_hl_device_496` | 0.84 | **0.116** | 22 | 5.10 | 5.30 |
| | `HLL_hl_device_445` | 1.05 | **0.075** | 24 | 7.23 | 5.30 |
| | *(+ 12 further kits up to 5.0 km)* | 1.29 – 5.00 | **0.159** | 24 | 6.59 – 8.08 | 5.30 – 5.39 |
| **Weighted Sensor Estimate** | **17 kits (`basis = "sensors"`)** | — | **1.000** | — | **6.83 µg/m³** | **± 5.30 µg/m³** |
| **Official Reference (comparison)** | `NL49701` (*Zaandam-Wagenschotpad*) | 2.75 | 1.000 | 24 | **7.17 µg/m³** | **± 0.00 µg/m³** |

Notice how `HLL_hl_device_378` (`0.29 km` away) is capped at `33.0%` weight by the `0.5 km` distance floor rather than dominating at `70%+`, producing a pooled sensor estimate (`6.83 µg/m³`) within **`0.34 µg/m³`** of the official RIVM reference monitor (`7.17 µg/m³`).

---

## 6. Reproduce This Example Yourself

Against a local Docker stack (`http://localhost:8000`) or our live Cloud Run backend (`https://luchtzorg-backend-103343530026.europe-west4.run.app`):

```bash
API="https://luchtzorg-backend-103343530026.europe-west4.run.app"   # or http://localhost:8000

# 1. Exact reproduction of Turn 1's 2025 WHO comparison + full R audit trail:
curl -s "$API/pm25/compare?lat=52.47590499&lon=4.8248332&radius_km=5.0&from=2025-01-01&to=2025-12-31&min_hours=18&cutoff=100.0&against=who" | python3 -m json.tool

# 2. Exact reproduction of Turn 2's weekday vs. weekend split:
curl -s "$API/pm25/weekday?lat=52.47590499&lon=4.8248332&radius_km=5.0&from=2025-01-01&to=2025-12-31&min_hours=18&cutoff=100.0" | python3 -m json.tool

# 3. Conversational end-to-end chat call:
curl -s -X POST "$API/chat" -H "Content-Type: application/json" \
  -d '{"message": "Hoe verhouden de fijnstofniveaus (PM2.5) rond de Zaanse Schans in 2025 zich tot de WHO-norm?"}' | python3 -m json.tool
```
