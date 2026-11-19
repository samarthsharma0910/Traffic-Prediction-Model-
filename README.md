# Saarthi — Live Traffic & Rush-Hour Prediction for India

Saarthi shows **current congestion**, **hour-by-hour forecasts** and **rush-hour windows** for
**118 Indian cities (664 monitoring zones, 35 states and union territories)**. A machine-learning model
predicts congestion from time, place, holidays and weather; when a TomTom key is configured, real measured
speeds replace the estimate for the zones you look at.

| | |
|---|---|
| **Backend** | Python 3.13 · FastAPI · scikit-learn · SQLite |
| **Frontend** | React 18 · Vite · Recharts · Leaflet |
| **Data** | Open-Meteo (weather, free), TomTom (optional live traffic), Natural Earth (coastlines), `holidays` (Indian public holidays) |
| **Model** | 3 gradient-boosted regressors · MAE 3.47 on a 0–100 score · 90.6 % level accuracy on a held-out month |
| **Size** | ≈ 3,200 lines of code · 25 automated backend tests |

> **Read this first — what is real and what is not.**
> Without a TomTom key there is **no real-time traffic**: "live" means the model evaluated at the current
> time using real live weather, and the UI labels it *ML-estimated*. The model's **training history is
> simulated** (no public hour-by-hour congestion dataset exists for Indian cities), so its accuracy figures
> describe how well it learned that pattern, not how it performs on real roads. Details in
> [Limitations](#17-limitations-and-honest-caveats).

---

## Table of contents

1. [What it does](#1-what-it-does)
2. [Tech stack and why](#2-tech-stack-and-why)
3. [Architecture](#3-architecture)
4. [Project structure](#4-project-structure)
5. [Data model](#5-data-model)
6. [Workflows](#6-workflows)
7. [The machine learning in depth](#7-the-machine-learning-in-depth)
8. [Live traffic integration (TomTom)](#8-live-traffic-integration-tomtom)
9. [API reference](#9-api-reference)
10. [Frontend](#10-frontend)
11. [Performance and caching](#11-performance-and-caching)
12. [Security and reliability](#12-security-and-reliability)
13. [Testing](#13-testing)
14. [Configuration](#14-configuration)
15. [Install and run](#15-install-and-run)
16. [Troubleshooting](#16-troubleshooting)
17. [Limitations and honest caveats](#17-limitations-and-honest-caveats)
18. [Roadmap](#18-roadmap)
19. [Credits and data sources](#19-credits-and-data-sources)

---

## 1. What it does

**Pages**

| Route | Purpose |
|---|---|
| `/` **Live map** | Opens on your current location (browser geolocation). Shows national KPIs, every zone on a map coloured by congestion level, a searchable/sortable list of cities with their rush-hour status, level filters, and (with a TomTom key) a live road-traffic layer. |
| `/city/<name>` | One city: current level and score, predicted rush windows, best/worst time to travel, a 24-hour forecast chart with an 80 % range band, a per-zone table and map, and a "typical week" heatmap. Pick any date (2023–2031) and a weather what-if (forecast / dry / light rain / heavy rain). |
| `/predict` | Forecast any city or single zone at any date and time (IST). Defaults to your nearest city. Result: score gauge, level, 80 % range, rush-hour yes/no, the day's rush windows and the day curve. |
| `/dashboard` | National view with cross-filtering: congestion ranking (cities or states, top 10/15/25, most/least), zones-by-level filter, a chart of how many cities are in rush at each hour (click an hour to filter), a sortable rush-window table, and the model's quality metrics. |

**Core concepts**

* **Zone** – a representative monitoring area in a city (CBD, Railway Station, Market Area, Ring Road, …). Bigger
  cities have 8–10 zones, smaller ones 5–6. Zones are *not* surveyed junctions.
* **Congestion score** – a 0–100 number. **Level** is derived from it everywhere (UI, API, training) from one place
  (`config.py`): **Low** < 30 ≤ **Moderate** < 55 ≤ **Heavy** < 75 ≤ **Severe**.
* **Rush hour** – a contiguous block of hours where the predicted score is in the top 40 % of that day's range
  and at least *Moderate* (see [§7.6](#76-rush-hour-detection)).

---

## 2. Tech stack and why

### Backend

| Technology | Role | Why this choice |
|---|---|---|
| **Python 3.13** | Language | The ML stack lives here; one language for data, model and API. |
| **FastAPI** + **Uvicorn** | HTTP API, static hosting of the built frontend, auto-generated docs at `/docs` | Typed request handling, JSON-first, easy to test with `TestClient`. Endpoints are plain `def`, so FastAPI runs them in a thread pool and CPU-bound model calls never block the event loop. |
| **scikit-learn** `HistGradientBoostingRegressor` | The forecasting model | Handles millions of rows quickly, supports **categorical features natively** and **quantile loss** (for the 80 % range). No GPU needed. |
| **pandas / NumPy** | Feature building, vectorised simulation | Whole-country predictions are one vectorised call (~16 k rows). |
| **joblib** | Model persistence | Fast, compressed (`traffic_model.joblib` ≈ 2.5 MB). |
| **SQLite** | Zone catalogue and live-reading log | Zero configuration, one file, plenty for ~660 rows of reference data. WAL mode is enabled. |
| **`holidays`** | Indian public holidays 2023–2031 | Correct movable-feast dates (Diwali, Holi, Eid …) without hand-maintained lists. |
| **`requests`** | Open-Meteo and TomTom calls | Simple, with explicit timeouts. |
| **shapely** *(dev only)* | Land check when generating zones | Used once by `tools/generate_zones.py`; not needed at runtime. |

### Frontend

| Technology | Role | Why |
|---|---|---|
| **React 18** + **Vite 5** | UI and build tooling | Fast dev server with hot reload; production build is a static folder FastAPI serves. |
| **React Router 6** | Client-side routing | `/`, `/city/:city`, `/predict`, `/dashboard`. The backend returns the app shell for any non-API path. |
| **Recharts** | Forecast area/line chart, bar charts | Declarative, composes well in React. |
| **Leaflet** + **react-leaflet** | Maps | Open-source, canvas rendering keeps 664 markers smooth. Base tiles from OpenStreetMap (no API key). |
| **Hand-written CSS** | Styling | One small stylesheet with design tokens; no UI framework dependency. Inter font. |

### External services

| Service | Used for | Key needed? |
|---|---|---|
| **Open-Meteo** | Current weather and a 7-day hourly precipitation forecast for every city | No |
| **TomTom Traffic** | *Optional.* Measured current vs free-flow speed (Flow Segment Data) and a live traffic raster layer (Flow tiles) | Yes (free tier) |
| **OpenStreetMap** | Map base tiles | No |
| **Natural Earth** | Land polygons used once to keep zones out of the sea | No (one-off download) |

---

## 3. Architecture

```
                         ┌───────────────────────────── Browser ─────────────────────────────┐
                         │  React SPA: Live · City · Predict · Dashboard                      │
                         │  geolocation → /api/nearest · polling every 60 s · Leaflet maps    │
                         └───────┬──────────────────────────────────────────────▲─────────────┘
                                 │ JSON (gzip)  /  PNG tiles                     │ index.html + /assets
                                 ▼                                               │
┌────────────────────────────────────────────── FastAPI  (app.py) ──────────────────────────────────────────┐
│  validation · error shape {"error": …} · routes · SPA fallback · GZip                                       │
└───────┬───────────────────────────────────────────────┬───────────────────────────────────┬────────────────┘
        │                                               │                                   │
        ▼                                               ▼                                   ▼
┌─────────────────────────┐              ┌──────────────────────────────┐      ┌────────────────────────┐
│ TrafficService          │  features    │ ml_model.py                  │      │ live_provider.py       │
│ (service.py)            │─────────────▶│ 3 × HistGradientBoosting     │      │ TomTom flow + tiles    │
│  · national curves cache│◀─────────────│ mean · p10 · p90             │      │ 5-min cache · budget   │
│  · overview / city /    │  scores      └──────────────────────────────┘      └───────────┬────────────┘
│    zone / predict logic │                                                                │ HTTPS
│  · rush-hour windows    │──────────▶ features.py  (shared by training and serving)       ▼
│  · hourly interpolation │                                                         api.tomtom.com
└───────┬─────────────────┘
        │ precipitation              ┌──────────────────────────────┐
        ▼                            │ SQLite  TrafficManagementDB  │   Location (664 zones)
┌─────────────────────────┐          │  · Location                  │   traffic_reading (live log)
│ weather.py              │          │  · traffic_reading           │
│ background thread, 1 h  │          │  · original schema tables    │
│ Open-Meteo (batched)    │          └──────────────────────────────┘
└─────────────────────────┘
        ▲
        └── api.open-meteo.com
```

**Design principle:** *predict once, slice many times.* All 664 zones × 24 hours of a day are predicted in a single
vectorised call and cached. The live map, city ranking, rush status, KPIs and dashboard are cheap slices of that
cache — no per-request model calls, no SQL aggregation.

---

## 4. Project structure

```
DBMS/
├── app.py                  FastAPI app: routes, validation, error handlers, serves frontend/dist
├── service.py              TrafficService: caching, forecasts, rush windows, overview/city/zone/predict
├── ml_model.py             Train / load / predict (3 gradient-boosted models) + evaluation
├── features.py             Feature engineering shared by training and serving (+ Indian holidays)
├── traffic_sim.py          Vectorised simulator that generates the training history
├── weather.py              Open-Meteo client with a background refresh thread
├── live_provider.py        TomTom client: speeds, tiles, cache, daily request budget, reading log
├── cities.py               The 118 cities + zone-kind definitions + zone placement geometry
├── database.py             SQLite schema, seeding (upsert), zone loading
├── config.py               Constants, level thresholds, IST helper, .env loader, TomTom settings
├── setup.py                One-shot: init DB → seed zones → train model
├── data/zones.json         The 664 land-checked zones (generated by tools/generate_zones.py)
├── tools/generate_zones.py One-off zone placement checked against Natural Earth coastlines
├── models/                 traffic_model.joblib (trained bundle) · metrics.json
├── TrafficManagementDB.sqlite  Created automatically on first run (git-ignored: it also holds local readings)
├── sql/01_create_tables.sql  The original MySQL schema this project grew out of
├── tests/test_app.py       25 backend tests
├── requirements.txt        Pinned runtime dependencies
├── requirements-dev.txt    Test + zone-generation extras (httpx, shapely)
├── .env.example            Template for .env (copy it; add your TomTom key)
├── render.yaml             Render Blueprint (free web service)
├── .env                    Local secrets (git-ignored) — TOMTOM_API_KEY
└── frontend/
    ├── index.html · vite.config.js · package.json
    ├── dist/               Production build (served by FastAPI)
    └── src/
        ├── main.jsx · App.jsx · api.js · utils.js · styles.css
        ├── components/     Layout · ui · DayChart · Heatmap · TrafficMap · Icon
        └── pages/          Live · City · Predict · Dashboard · NotFound
```

---

## 5. Data model

SQLite file `TrafficManagementDB.sqlite`, created automatically on first start and git-ignored (it also stores this machine's live readings). Only two tables carry live data; the rest are the project's original
schema (kept for continuity with `sql/01_create_tables.sql`) and are currently empty.

**`Location`** — one row per zone (664 rows). `UNIQUE (city, zone_kind)`; seeding is an upsert so `location_id`s stay stable.

| Column | Meaning |
|---|---|
| `location_id` (PK) | Zone id used by the API |
| `location_name`, `road_name` | Display names, e.g. "Pune - Railway Station" |
| `city`, `state` | Where it is |
| `latitude`, `longitude` | Zone coordinates (land-checked) |
| `zone_kind` | CBD, Railway Station, Market Area, Ring Road, Highway Bypass, Residential Arterial, IT / Business Park, Airport Corridor, Old City, University / Hospital |
| `population_m` | City metro population in millions (approximate; scales expected congestion in the simulator) |

**`traffic_reading`** — append-only log of *measured* readings (written only when TomTom is enabled).
Columns: `location_id`, `reading_datetime` (IST), `congestion_score`, `congestion_level`, `current_speed_kmph`,
`free_flow_speed_kmph`, `precip_mm`, `source` (`'tomtom'`). Indexed by `(location_id, reading_datetime DESC)`.
This is the raw material for retraining on real data (see [Roadmap](#18-roadmap)).

**Original-schema tables** (unused today): `Traffic_Signal`, `Driver`, `Vehicle`, `Violation_Type`,
`Traffic_Officer`, `Traffic_Violation`.

The trained model is **not** in the database: it is a joblib bundle in `models/` containing the three
regressors, the city/zone-kind encoders and the evaluation metrics.

---

## 6. Workflows

### 6.1 Training (`python setup.py`) — only needed to retrain

```
cities.CITIES (118) ──┐
                      ├─ tools/generate_zones.py ──▶ data/zones.json (664 land-checked zones)   [done once by a developer]
Natural Earth land ───┘

setup.py
  1. database.init_database()          create tables + indexes
  2. database.seed_locations(zones)    upsert 664 rows from data/zones.json into Location
  3. ml_model.train(load_zones())
       a. traffic_sim.simulate()       400 days × 24 h × 664 zones  = 6.37 M hourly rows
       b. time-based split             last 28 days held out for testing
       c. fit 3 models                 mean · 10th percentile · 90th percentile
       d. evaluate                     MAE, RMSE, R², level accuracy, peak-hour accuracy, band coverage, baseline
       e. save                         models/traffic_model.joblib + models/metrics.json
```

You do **not** need this on a fresh checkout: `models/traffic_model.joblib` is included and `app.py` creates the database itself.
Training takes roughly 5–10 minutes depending on the CPU (8 cores). Re-run `python setup.py` whenever zones change (zone
coordinates are model inputs, so the model must be retrained to match).

### 6.2 Server start (`python app.py`)

1. `config.py` loads `.env` (so `TOMTOM_API_KEY` is available) and builds settings. `database.ensure_seeded()` creates the SQLite
   schema and upserts the 664 zones from `data/zones.json`, so a fresh checkout needs no database setup.
2. `TrafficService.__init__` loads the model bundle and zones, builds the per-zone feature table and the
   city→zones index. If the DB contains a city/zone the model never saw it raises a clear "run `python setup.py`" error.
3. `service.start()` launches the **weather thread**. Its first refresh fetches all cities from Open-Meteo, then calls
   `service.warm()`, which precomputes today's national curves and the overview so the first visitor isn't slow.
4. Uvicorn serves the API and `frontend/dist`.

### 6.3 What happens when you open the Live map

```
Browser                                    FastAPI / TrafficService
───────                                    ────────────────────────
GET /                                  ──▶ SPA fallback returns frontend/dist/index.html
GET /assets/*.js|css                   ──▶ static files
GET /api/overview                      ──▶ service.overview():
                                              cache hit (same minute, same weather & live version)? return it
                                              else: _point(now) → hourly curves for today (cached) → interpolate to HH:MM
                                                    overlay any fresh TomTom readings (per-zone)
                                                    aggregate per city, rank, compute "in rush / next rush"
navigator.geolocation (browser)            
GET /api/nearest?lat=&lon=             ──▶ nearest zone by distance (≤ 60 km) → city + zone id
[TomTom enabled]
POST /api/live/refresh {city}          ──▶ fetch measured speeds for that city's zones (8 in parallel,
                                              5-min cache, daily budget) → logged to traffic_reading
GET /api/overview (again)              ──▶ now includes the measured zones
…every 60 s: poll /api/overview; every 5 min: refresh the visitor's city
```

### 6.4 What happens when you ask for a prediction

`POST /api/predict {city, zone_id?, datetime, weather}`:

1. **Validate** — city exists; `zone_id` belongs to that city; datetime is `YYYY-MM-DDTHH:MM` with **no timezone**
   (it is interpreted as IST) and between 2023-01-01 and 2031-12-31; weather ∈ auto/dry/light/heavy. Any failure → `400 {"error": …}`.
2. **Weather** — `auto` uses the Open-Meteo forecast for that hour if one exists (yesterday … +6 days); otherwise
   dry weather is assumed and the response says so. `dry/light/heavy` force 0 / 2 / 10 mm/h.
3. **Features** — one row per (zone, hour) for that day, built by `features.make_features` (the same function used in training).
4. **Predict** — the three models give expected score, 10th and 90th percentile for all 24 hours.
5. **Interpolate** — linear blend between the hour before and after the requested minute (so 08:59 and 09:00 agree);
   at 23:xx it blends with 00:00 of the next day.
6. **Derive** — level from the score (and for the range ends), rush windows from the day curve, "in rush now?" and the nearest window.
7. **Respond** — score, level, range, rush flags/windows, precipitation used, weather mode, holiday name, 24-hour curve.

### 6.5 What happens on a city page

`GET /api/city/Pune?date=&weather=` → today's national curves (cached) → slice the city's zones → city curve =
mean of its zones → rush windows, best/worst hour (06:00–22:00), zone rows (live if available, otherwise the model's
current value; for other dates or what-if weather, each zone's *peak* for the day) and the **typical week**
(seven dry, non-holiday reference days, cached). With TomTom enabled and the date being today, the city's zones are refreshed first.

### 6.6 What happens on the dashboard

The page makes three requests (`/api/overview`, `/api/rush-hours?date=`, `/api/model-info`) and does the rest in the
browser: grouping cities into states, counting zones per level, building the "cities in rush by hour" histogram from
each city's windows, and filtering/sorting the table. Selecting a level, a bar or an hour re-filters the other panels
without another server call.

---

## 7. The machine learning in depth

### 7.1 Problem framing

*Given where (zone), when (hour, weekday, month, holiday) and the weather (precipitation), what congestion score
(0–100) do we expect — and how uncertain are we?*

The model is a **regressor**, not a classifier: level (Low…Severe) and rush hour are derived from the predicted
score by fixed rules, so every figure in the UI is consistent with every other.

### 7.2 Features (`features.py`)

13 inputs, built identically for training and serving:

| Feature | Notes |
|---|---|
| `hour` | Float; supports minutes at serving time |
| `hour_sin`, `hour_cos` | Cyclical encoding so 23:00 and 00:00 are neighbours |
| `dow`, `is_weekend` | Day of week |
| `month` | Seasonality (monsoon, festival season) |
| `is_holiday` | National Indian public holidays (`holidays` package) |
| `precip_mm` | Precipitation, mm per hour |
| `lat`, `lon`, `log_pop` | Where the zone is and how big its city is |
| `city_code`, `kind_code` | **Categorical**: city and zone kind |

**Deliberately excluded:** vehicle counts and speeds. They are *consequences* of congestion, so using them leaks the
answer and makes forecasting impossible. (The project's original version made exactly this mistake.)

### 7.3 The training data (`traffic_sim.py`)

No public hour-by-hour congestion dataset exists for Indian zones, so history is simulated from documented
qualitative patterns — vectorised, so 6.37 million rows take seconds:

* **City intensity** = `38 + 8·log2(population_m + 0.6) + bias`, with extra bias for cities known to be worse than their
  size suggests (Bengaluru, Pune, Mumbai, Kolkata, Hyderabad, …). Multiplied by a per-zone-kind gain (CBD highest, airport/bypass lowest).
* **Hourly demand profile per zone kind** built from Gaussian bumps: Indian double peak (≈ 9–10 h and ≈ 18–19 h),
  a late-evening market peak, IT-park peaks that vanish on weekends, night-time truck traffic on bypasses,
  an all-day plateau in the old city, etc. Weekends and public holidays switch to a separate "off-day" profile.
* **Weather**: wet-day probability by region and month (south-west monsoon on the west coast, north-east monsoon
  on the south-east coast …); rain adds congestion, more in flood-prone cities and more when roads are already busy.
* **Noise**: a persistent per-zone offset, a shared city-day shock, and hourly noise — so the model cannot be perfect.
* **Coverage in time**: 400 days (so all four seasons appear), ending the day before training.

### 7.4 The model (`ml_model.py`)

Three `HistGradientBoostingRegressor`s with the same settings (max 63 leaves, learning rate 0.1, min 100 samples per
leaf, L2 = 1.0, early stopping, categorical handling for city and zone kind):

| Model | Loss | Output |
|---|---|---|
| `mean` | squared error | expected score |
| `lo` | quantile 0.10 | low end of the 80 % range |
| `hi` | quantile 0.90 | high end of the 80 % range |

Predictions are clipped to 0–100 and the range is forced to bracket the mean.

### 7.5 Evaluation

A strict **time-based split**: the last 28 days are held out (a random split would leak neighbouring hours of the same
day into the test set). 5.93 M rows train, 0.45 M test. Results (also shown on the Dashboard):

| Metric | Value | Meaning |
|---|---|---|
| MAE | **3.47** | Average error on the 0–100 score |
| RMSE | 4.39 | |
| R² | 0.934 | |
| Baseline MAE | 4.04 | Historical average per zone × weekday × hour (no weather) |
| MAE on rainy hours | **3.74** vs baseline 9.65 | The model's main advantage is that it uses the weather |
| Level accuracy | 90.6 % (100 % within one level) | Predicted level vs actual level |
| Peak hour within ±1 h | ≈ 89 % | Predicted busiest hour of a zone-day vs the real one |
| 80 % range coverage | 80.1 % | The band is well calibrated |

> These numbers are measured against *simulated* data. They show the model learned the pattern correctly and that its
> uncertainty band is honest; they are **not** a claim about accuracy on real roads. The rainy-hours gain over the
> baseline is partly by construction, because the simulator makes rain matter.

### 7.6 Rush-hour detection

Implemented in `service.rush_windows` and applied to a city's (or zone's) 24-hour predicted curve:

1. Let `lo` and `hi` be the day's minimum and maximum predicted score.
2. If `hi < 30` (never even Moderate) **or** `hi − lo < 12` (no real daily swing) → **no distinct rush hour**.
3. Threshold = `max(lo + 0.6·(hi − lo), 30)`.
4. Hours at or above the threshold form runs; runs separated by a single dip hour are bridged.
5. Each run becomes a window `{start, end, label, peak_hour, peak_score, peak_level}`.

"In rush now" and "next rush in …" come from comparing the current time with today's windows (and tomorrow's if
today's are over). Because the rule is relative to each day's range, a rainy day shifts and widens windows naturally.

### 7.7 Speed estimate

Where no measured speed exists the UI shows an *estimated* speed: `free_flow × (1 − 0.8 × score/100)`, with free-flow
35 km/h by default (70 for highway bypasses, 55 for ring roads and airport corridors). It is flagged "est." in the UI.

---

## 8. Live traffic integration (TomTom)

Enabled when `TOMTOM_API_KEY` is set (in `.env` or the environment). Two separate mechanisms:

**1. Measured zone status — TomTom Flow Segment Data**

* For a zone's coordinates TomTom returns the **current speed** and **free-flow speed** of the nearest road segment.
* Converted to the same 0–100 score: `score = clip(120 × (1 − current / free_flow), 0, 100)`
  (ratio 0.75 → 30, the Low/Moderate boundary; 0.54 → 55; 0.375 → 75).
* Readings with TomTom confidence below 0.3 are ignored. Valid readings are cached for **5 minutes**, fetched
  **8 at a time**, and appended to `traffic_reading`.
* Measured zones show no model range (it would be meaningless) and no "est." tag; the badge reads
  *"TomTom live · N zones measured"*.
* Fetched **on demand**: when the Live page locates you, and when you open a city page for today.

**2. Live traffic layer — TomTom Flow tiles**

* A real-time road-colouring raster overlay for the whole map (visible when zoomed in).
* Requests go to `/api/tiles/flow/{z}/{x}/{y}.png`; the backend adds the key and caches each tile for 60 s,
  so **the key is never sent to the browser**.

**Quota protection:** non-tile calls are capped at `TOMTOM_DAILY_BUDGET` (default 2,200 of the free 2,500/day).
Once spent, the app silently falls back to ML estimates until midnight IST. The tile proxy has its own daily cap (`TOMTOM_TILE_DAILY_BUDGET`, default 20,000 upstream fetches). Usage is visible in `/healthz`
and `/api/overview` under `live`.

**Why only some zones are measured:** ~10 calls per city × 118 cities would exceed the free quota quickly, so
measured speeds are fetched for the cities people actually view. Everything else stays ML-estimated and labelled as such.

**Caveat:** a reading is the road segment *nearest the zone's coordinates* — a sample, not an area average — and can
be a minor street.

---

## 9. API reference

Base URL `http://127.0.0.1:8000`. Interactive docs: `/docs`. All errors are `{"error": "message"}`:
`400` invalid input, `404` unknown city/zone/path, `500` unexpected.

| Method & path | Purpose | Key parameters |
|---|---|---|
| `GET /api/overview` | National snapshot: KPIs, every city (score, level, rush status, weather), every zone (score, level, speed), `live` quota status | — |
| `GET /api/cities` | City list with their zones (for dropdowns) | — |
| `GET /api/city/{name}` | Full city detail: 24 h curve + range, rush windows, best/worst hour, zones, typical week, weather | `date=YYYY-MM-DD`, `weather=auto\|dry\|light\|heavy` |
| `GET /api/zone/{id}` | Same idea for a single zone | `date`, `weather` |
| `GET` / `POST /api/predict` | Forecast for a city or zone at a date-time | `city` *(required)*, `zone_id`, `datetime=YYYY-MM-DDTHH:MM` (IST, no timezone), `weather` |
| `GET /api/rush-hours` | Rush windows, peak hour and peak level for every city | `date` |
| `GET /api/nearest` | Nearest zone to a point (within 60 km) | `lat`, `lon` |
| `POST /api/live/refresh` | Fetch measured TomTom speeds for one city (no-op without a key) | body `{"city": "Delhi"}` |
| `GET /api/tiles/flow/{z}/{x}/{y}.png` | Proxied live traffic tile | tile coordinates |
| `GET /api/model-info` | Training/evaluation metrics | — |
| `GET /healthz` | Status, zone count, weather state (`weather`: cities loaded, last success, last error), live-provider state, TomTom budgets used | — |

Example:

```bash
curl "http://127.0.0.1:8000/api/predict?city=Bengaluru&datetime=2026-11-16T18:30&weather=dry"
```

---

## 10. Frontend

**Routing** — `App.jsx` defines four routes plus a 404; `Layout.jsx` supplies the header, mobile menu and footer.

**Data access** (`api.js`)

* `useApi(url, {interval})` — fetches, keeps the previous data while reloading, ignores out-of-order responses,
  optionally polls (skipped while the tab is hidden).
* `useUserLocation()` — wraps browser geolocation, then asks `/api/nearest` which zone/city is closest.
* `useTitle()` — sets the tab title per page.

**Components**

| Component | Role |
|---|---|
| `TrafficMap` | Leaflet map; canvas circle markers coloured by level (worst drawn on top), popups, user location dot, fly-to focus, optional live tile layer |
| `DayChart` | 24 h forecast: line = expected score, shaded band = 80 % range, tinted columns = rush windows, "Now" marker, level threshold guides |
| `Heatmap` | 7 × 24 typical-week grid |
| `ui.jsx` | `LevelBadge`, `Metric`, `Panel`, `ScoreBar`, `RushStatus`, `SourceBadge`, `ErrorBox`, `Skeleton` |

**Interaction highlights**

* *Live map*: geolocation on load, level filter chips, search + sort, click a city to fly to it, refresh every minute,
  the visitor's city re-measured every 5 minutes (with TomTom).
* *City*: date picker and weather what-if re-query the API; the page is keyed by city so state resets on navigation.
* *Predict*: a link such as `/predict?city=Mumbai&zone=12` runs the prediction immediately.
* *Dashboard*: cross-filtering (level → ranking, bar → table, hour → table), sortable columns with `aria-sort`.

**Design** — light theme, Inter, a restrained blue primary, pastel level badges (Low/Moderate/Heavy/Severe),
bordered panels and uppercase-header tables. Responsive layout (checked down to roughly 520 px wide).

---

## 11. Performance and caching

| What | How | Effect |
|---|---|---|
| National day curves | One vectorised prediction of 664 zones × 24 h, cached per `(date, weather override, weather version)`, max 40 entries | Everything "live" is a slice of this |
| Overview payload | Cached per `(minute, weather version, live-data version)` | Repeated polls ≈ 10 ms |
| Typical-week grids | Cached per `(zones, 7 reference dates)` | City pages after the first are instant |
| Warm-up | After every weather refresh the service precomputes today's overview | The first visitor isn't slow |
| Weather | Background thread; one batched call per 40 cities, 2 s apart, hourly; batches succeed or fail independently; failures retry only the missing cities with backoff (1 → 15 min, honouring `Retry-After`) | No request ever waits on Open-Meteo, and a rate limit (HTTP 429, common on shared cloud hosts) heals itself |
| Payload size | Overview zones carry only the fields the map needs; GZip for responses ≥ 1 KB | ≈ 20 KB over the wire |
| TomTom | 5-min reading cache, 60-s tile cache, 8-way parallel fetch, daily budget | Quota-safe |

Measured on the development machine (warm): overview ≈ 10 ms, city page ≈ 6 ms, prediction ≈ 35 ms,
first cold city page ≈ 0.2 s.

---

## 12. Security and reliability

* **Secrets** — the TomTom key lives only in `.env` (git-ignored) and is never returned to the browser; tiles are proxied.
* **Input validation** — every query/body field is validated; invalid input never reaches the model; errors use one JSON shape.
* **Path safety** — the SPA fallback resolves paths and refuses anything outside `frontend/dist` (a test covers `..` traversal).
* **Graceful degradation** — Open-Meteo down or rate-limited → last good data per city, or dry weather with the UI told so (the reason is shown in `/healthz` → `weather.last_error`); TomTom down or
  budget spent → ML estimates; frontend not built → a clear 503 page pointing to `npm run build`.
* **Response headers** — `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY` and a strict `Referrer-Policy` on every response.
* **Threading** — the weather thread never dies on errors; cache computation is lock-protected.
* **Timezone** — India has no DST, so IST is a fixed UTC+05:30 offset (avoids a `tzdata` dependency on Windows).
  Timestamps are naive IST throughout.
* **Output safety** — the React app renders all data as text (no raw HTML injection).

---

## 13. Testing

`python tests/test_app.py` — **25 tests** using FastAPI's `TestClient`. They set `TRAFFIC_DISABLE_WEATHER=1` and
`TRAFFIC_DISABLE_LIVE=1`, so they never touch the network or spend TomTom quota.

| Area | What is checked |
|---|---|
| Health / routing | `/healthz`, SPA fallback, unknown API path → 404, unknown city → 404, path traversal blocked |
| Coverage | ≥ 100 cities, > 500 zones, every score in 0–100, every level valid, every coordinate inside India's bounding box |
| Performance | Warm `/api/overview` averages < 150 ms |
| ML behaviour | 03:00 much quieter than 18:30 and not rush; evening is rush; heavy rain raises congestion; a business-park zone is much busier on a weekday than a Sunday; a big city is busier than a small one; the 80 % range brackets the score |
| Correctness | No jump across the hour boundary (interpolation); 23:30 works (midnight wrap) |
| Validation | Missing city, bad datetime, timezone suffix, out-of-range year, bad weather, non-numeric / foreign zone id, non-object JSON body, bad date, bad lat/lon |
| Endpoints | POST predict, city detail + zone detail shape, rush table, nearest zone (Delhi) and "no zone within 60 km" |
| Rush logic | Double-peak day → two windows; flat or quiet day → none |
| Weather resilience | A rate-limited batch keeps the good batches and retries only the missing cities; earlier data survives a failed refresh; error text includes Open-Meteo's reason and `Retry-After`; backoff grows and is capped (network mocked) |
| Shipping | Security headers present; API title is Saarthi; database seeding is idempotent (664 zones, no duplicates); the TomTom tile proxy honours its daily cap, caches repeats and rejects out-of-range tiles (network mocked) |

Frontend interactions were additionally exercised in a real headless browser during development; there is no
automated frontend test suite yet (see [Roadmap](#18-roadmap)).

---

## 14. Configuration

Environment variables (a `.env` file next to `app.py` is read automatically; real environment variables win):

| Variable | Default | Effect |
|---|---|---|
| `TOMTOM_API_KEY` | *(unset)* | Enables measured speeds and the live traffic layer |
| `TOMTOM_DAILY_BUDGET` | `2200` | Max non-tile TomTom calls per IST day |
| `TOMTOM_TILE_DAILY_BUDGET` | `20000` | Max upstream live-tile fetches per IST day (cached tiles are free) |
| `PORT` | `8000` | Server port |
| `HOST` | `127.0.0.1` | Bind address (use `0.0.0.0` to serve other devices on your network) |
| `TRAFFIC_DISABLE_LIVE` | *(unset)* | `1` disables TomTom even if a key exists (used by tests) |
| `TRAFFIC_DISABLE_WEATHER` | *(unset)* | `1` skips the weather thread (used by tests) |

Constants worth knowing (`config.py`, `service.py`): level thresholds `30 / 55 / 75`; supported date range
2023-01-01 … 2031-12-31 (the holiday table's range); nearest-zone radius 60 km.

---

## 15. Install and run

**Requirements:** Python 3.13 (what it was built and tested on; the pinned versions support 3.10+ but are untested there).
Node 18+ is only needed if you modify the frontend.

```bash
# 1. backend dependencies (versions are pinned - see requirements.txt)
pip install -r requirements.txt

# 2. (optional) real-time traffic: copy .env.example to .env and add your TomTom key
copy .env.example .env      # Windows        (macOS/Linux: cp .env.example .env)

# 3. run. The trained model and the built frontend are in the repository, and the SQLite
#    database is created automatically on first start - nothing else to set up.
python app.py               # http://127.0.0.1:8000   (API docs at /docs)

# tests (needs the dev extras)
pip install -r requirements-dev.txt
python tests/test_app.py

# only if you change zones, upgrade scikit-learn, or want to retrain (about 5-10 min)
python setup.py
```

**Working on the frontend** (hot reload; run `python app.py` in another terminal):

```bash
cd frontend
npm install
npm run dev                # http://localhost:5173, proxies /api to :8000
npm run build              # rebuilds frontend/dist, which FastAPI serves
```

**Changing the zones:** edit `cities.py`, run `python -I tools/generate_zones.py <path-to-ne_10m_land.geojson>`
(needs `pip install shapely`; the file is Natural Earth's `ne_10m_land.geojson`), then `python setup.py` to reseed and retrain.

### Deploying to Render (free tier)

The repository contains a Render Blueprint (`render.yaml`), so deployment is a few clicks. The built frontend, the trained
model and the pinned dependencies are all in the repo, so Render needs no Node build and no training step.

1. **Push the repo to GitHub** (`git push`).
2. In the [Render dashboard](https://dashboard.render.com): **New → Blueprint**, connect GitHub, choose this repository.
3. Render reads `render.yaml` and asks for **`TOMTOM_API_KEY`**. Paste your key (or leave it empty to run on ML estimates only). Click **Apply**.
4. Wait for the build (a few minutes). Your site is at `https://saarthi-….onrender.com`; `/healthz` should return `{"status":"ok",…}`.

The service runs `uvicorn app:app --host 0.0.0.0 --port $PORT --no-access-log` on **Python 3.13.4** (pinned by the `.python-version`
file, which Render honours for every kind of service). HTTPS is provided by
Render, which also makes the browser's "use my location" work.

**If you create the service by hand instead of using the Blueprint** (New → Web Service), `render.yaml` is *not* applied. Use:

| Setting | Value |
|---|---|
| Runtime | Python 3 |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn app:app --host 0.0.0.0 --port $PORT --no-access-log` |
| Health check path | `/healthz` |
| Environment | `TOMTOM_API_KEY` (optional). `PYTHON_VERSION=3.13.4` is optional — `.python-version` already pins it. |

> **Do not let Render pick its default Python.** It currently defaults to a newer release (3.14) for which the pinned
> `numpy`/`pandas` have no prebuilt wheels: the build compiles them from source (12+ minutes) and the server then
> crashes with `Exited with status 139` (a segmentation fault). `app.py` now refuses to start on Python 3.14+ with a clear message.

**What to expect on the free plan**

| Limit | Effect |
|---|---|
| Spins down after ~15 min without traffic | The next visit waits ~30–60 s for a cold start (the app loads the model, then computes its first national forecast). To avoid it, ping `/healthz` every ~10 min from a free uptime monitor — one always-on service fits in the 750 free hours per month. |
| 512 MB RAM, fraction of a CPU | The app uses ≈ 210 MB. Forecasts are noticeably slower than on a laptop; the first page after a cold start can take tens of seconds. |
| Ephemeral disk | The SQLite file is recreated on every start, so logged TomTom readings are not kept between restarts. Nothing else depends on it. |

**Public-site cautions:** anyone can reach the site, so the TomTom caps matter — `TOMTOM_DAILY_BUDGET` (default 2,200 data calls/day)
and `TOMTOM_TILE_DAILY_BUDGET` (default 20,000 upstream tile fetches/day). When a cap is reached the app falls back to ML
estimates until midnight IST. Check your numbers against your TomTom plan. The API key lives only in Render's environment settings.

> The deployment files were verified by running the exact start command locally on Windows. A run on Linux (Render's OS) was
> not possible in the development environment; the pinned package versions provide Linux wheels, so it is expected to work,
> and `/healthz` plus the Render logs will show immediately if it does not.

---

## 16. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "Frontend not built" page (503) | Run `cd frontend && npm install && npm run build`. The API still works at `/docs`. |
| `RuntimeError: Database has zones the model never saw` | Zones and model are out of sync. Run `python setup.py`. |
| Port 8000 already in use | Set another port: PowerShell `$env:PORT=8001; python app.py`. |
| Badge says *ML-estimated* although you set a key | The key must be in `.env` next to `app.py` (or the environment) **before** starting the server; restart it. Check `/healthz` → `live.enabled`. |
| Live layer invisible | TomTom flow tiles show road colouring only when zoomed in; zoom to a city. |
| Location prompt never appears / is denied | Browsers allow geolocation only on `localhost` or HTTPS. The app falls back to the all-India view. |
| Warning or error loading `traffic_model.joblib` | scikit-learn version differs from the pinned 1.7.2 (the model is a pickle). Install the pinned versions, or retrain with `python setup.py`. |
| Render site very slow on first visit | Free-plan cold start (see *Deploying to Render*). Wait up to a minute, or keep it warm with an uptime monitor pinging `/healthz`. |
| Render log: `Exited with status 139` (segfault) or `Using Python version 3.14` | The service is running an unsupported Python. Make sure `.python-version` (3.13.4) is in the repo, or set `PYTHON_VERSION=3.13.4`, then **Manual Deploy → Clear build cache & deploy**. |
| Old page after an update | Hard refresh (Ctrl+F5) so the browser loads the new build. |
| TomTom suddenly stops updating | The daily budget may be spent — see `/healthz` → `live.used_today`. It resets at midnight IST. |
| Logs show `weather request failed … HTTP 429` / weather shows "unavailable" | Open-Meteo is rate-limiting your host's IP (typical on free shared cloud hosting). It is a warning, not a crash: the app keeps serving with dry-weather fallback, retries automatically with backoff, and fills in as soon as it is allowed. Check `/healthz` → `weather` (`cities` of `of`, `last_error`). |

---

## 17. Limitations and honest caveats

1. **Simulated training data.** The model learned a plausible *pattern*, not real Indian traffic. Its metrics prove
   it learned that pattern and that its range is calibrated; they say nothing about real-road accuracy.
2. **No real-time data without a key.** "Live" then means "model at the current time + real weather".
3. **TomTom coverage is partial by design** (quota): only the cities you view are measured; each reading is a
   single-road sample near the zone's coordinates.
4. **Zones are representative areas**, not surveyed junctions; positions are generated around each city centre and
   checked to be on land. Population figures are approximate.
5. **National holidays only.** Regional festivals and local events are not modelled.
6. **Rush windows look alike across cities.** The simulator gives every city a similar double peak, so most cities
   show ≈ 08:00–11:00 and 17:00–21:00. With real data these would diverge.
7. **Congestion score is a constructed index**, not a standard unit; with TomTom it is derived from the speed ratio
   (`120 × (1 − current/free-flow)`), which is a reasonable but arbitrary mapping.
8. **Single process, in-memory caches.** Fine for a demo or a small deployment; scaling out would need a shared cache.
9. **Forecast horizon.** Weather is forecast about a week ahead; beyond that, dry weather is assumed.

---

## 18. Roadmap

* **Retrain on real data** — `traffic_reading` already accumulates measured TomTom readings. A scheduled collector
  across all cities, then blending real rows into training (weighted above simulated ones), is the biggest quality win.
* Regional holidays and events; school-term calendars.
* Frontend test suite (component + end-to-end) and CI.
* Shared cache (Redis) and a production server setup if deployed publicly.
* Per-road routing/ETA using TomTom Routing, and alerts ("tell me when X clears").
* Model refresh job and drift monitoring against measured readings.

---

## 19. Credits and data sources

* **Open-Meteo** — weather and forecasts (free, no key). <https://open-meteo.com>
* **TomTom Traffic API** — optional live traffic. <https://developer.tomtom.com>
* **OpenStreetMap** contributors — map tiles. <https://www.openstreetmap.org/copyright>
* **Natural Earth** — land polygons used to keep zones on land. <https://www.naturalearthdata.com>
* **python-holidays** — Indian public holidays.
* Libraries: FastAPI, scikit-learn, pandas, NumPy, React, Vite, Recharts, Leaflet.

The project grew out of a DBMS course schema (`sql/01_create_tables.sql`); the original Flask prototype was
rewritten into the current architecture.
