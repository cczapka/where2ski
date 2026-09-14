# where2ski – concept for the Android app

Goal: tell a Munich-based skier **where and when** conditions are good in the
Bavarian Alps, Tyrol (Snow Card Tirol) and the Salzburg area, with a focus on
free skiing (off-piste, lift-accessed) but also usable for piste days.

This document refines the idea into factors, data sources, a snow-quality
model, a scoring scheme and an architecture. It replaces the Bergfex-scraping
approach of the Python prototype ([where2ski_py](https://github.com/cczapka/where2ski_py))
with open, documented data.

---

## 1. Scope and modes

| Aspect | Decision |
|---|---|
| Region | Bavarian Alps (DE-BY), Tyrol (AT-07 incl. East Tyrol), Salzburg (AT-05). Extendable. |
| Resorts | Curated registry (see §7) of the major resorts only: the larger Snow Card Tirol areas within ~2.5 h of Munich plus the main Bavarian and Salzburg resorts. Very small Snow Card areas are deliberately left out. |
| Modes | **Freeride** and **Piste**. Same data, different weights and blockers. |
| Horizon | Today + 9 days (matches the Python prototype); confidence decays with lead time. |
| Passes | Each resort carries a `passes` list (`snowcard_tirol`, `ski_amade`, …). "Snow Card Tirol only" is a filter, not a hard rule. |
| Output | A ranked list per day, a day × resort matrix ("when"), a map, and a resort detail page with the reasoning ("why"). |

Free skiing is interpreted as lift-accessed off-piste within resorts. Ski
touring is enjoyed too but is out of scope for now; the same snow-quality and
avalanche model would apply to touring zones later.

---

## 2. Factors that decide whether it is "nice to ski"

Your list (snowfall, weather, temperature, sun, height) is the right core.
Below is the refined set, with how each is measured and which source feeds it.

### 2.1 Snow supply

| Factor | Why it matters | Measure | Source |
|---|---|---|---|
| New snow last 24/48/72 h | Powder; the single strongest freeride signal | Station snow-height differences (HS_t − HS_t−24h) with settling correction; forecast snowfall by elevation band | Stations (§3.2), Open-Meteo / GeoSphere (§3.1) |
| Forecast snowfall next 1–9 days | Plan the trip; "snow Friday, bluebird Saturday" pattern | Daily snowfall sum at base/mid/top elevation | Open-Meteo, GeoSphere AROME |
| Base depth (HS) | Enough cover for off-piste rocks and for the piste to be open at all | HS at a mid-mountain station; thresholds: freeride ≥ 80–100 cm alpine, ≥ 120 cm in forested/blocky terrain; piste ≥ 30–40 cm | Stations, SNOWGRID (AT) |
| Snow line / freezing level | Decides rain vs snow per elevation band | `freezing_level_height` hourly; compare with band elevations | Open-Meteo |

### 2.2 Snow quality (the "is it still good?" question)

This is the part no public site does well; see §4 for the model. Inputs:

| Input | Why | Source |
|---|---|---|
| Air temperature history at band elevation | Hours above 0 °C since the last snowfall → melt | Stations, Open-Meteo `past_days` |
| Snow-surface temperature (where measured) | The most direct melt/refreeze signal: 0 °C surface = melting | LWD stations (Bavaria, Tyrol) |
| Night minimum / refreeze | Melt + refreeze = crust; repeated cycles = corn snow | Stations, forecast |
| Sun / global radiation since snowfall, weighted by aspect | Sun cooks south faces first; north faces keep powder | Stations (global radiation), Open-Meteo `sunshine_duration`, aspect roses (§5) |
| Wind during and after snowfall | Wind-pressed, wind-slab, stripped ridges | Stations (gusts), forecast |
| Rain on snow | Ruins everything below the snow line | Forecast precipitation type / freezing level |
| Days since last ≥ 10 cm snowfall | Simple ageing | Derived |

### 2.3 Weather on the day

| Factor | Why | Measure | Source |
|---|---|---|---|
| Sunshine hours | Enjoyment, visibility, but also melting | Daily `sunshine_duration` | Open-Meteo |
| Visibility / low cloud / fog | Freeriding in flat light is dangerous and no fun; valley fog with sun above (inversion) favours high resorts | `cloud_cover_low`, `visibility`, temperature at 850/700 hPa vs valley | Open-Meteo |
| Temperature comfort | −15 … +3 °C is pleasant; colder = misery, warmer = slush | Mid-station daytime temperature | Open-Meteo |
| Wind / gusts at ridge height | Lift closures (gusts > 60–70 km/h), wind chill, wind-affected snow | `wind_gusts_10m` at top elevation | Open-Meteo, stations |
| Precipitation on the day | Snowing all day can still be great for powder, rain never is | Hourly precipitation and type | Open-Meteo |

### 2.4 Safety

| Factor | Why | Measure | Source |
|---|---|---|---|
| Avalanche danger level per micro-region and elevation | Freeride mode must respect it; level 4–5 blocks, 3 penalises heavily | CAAML v6 bulletin: danger rating, elevation boundary, tendency | lawinen.report / EAWS (§3.3) |
| Avalanche problems with aspects and elevations | Wind slab on N–E above 2200 m etc. maps directly onto the aspect model | CAAML `avalancheProblems[].aspects / elevation` | same |

### 2.5 Terrain and altitude

| Factor | Why | Measure | Source |
|---|---|---|---|
| Elevation bands (base / mid / top) | Everything above is evaluated per band; high resorts win in warm spells and in inversions | Min/max run elevation, lift top stations | OpenSkiMap (§3.4) |
| Aspect distribution ("ski rose") | North-facing terrain holds powder for days, south faces crust and later give corn | Bearing of each run segment from OSM geometry + DEM, aggregated per resort | OpenSkiMap runs + DEM, OpenSkiStats method |
| Off-piste terrain share, tree skiing | Trees help in flat light and wind; open alpine bowls need visibility | OSM tags (`piste:type`, `natural=wood`), slope from DEM | OSM, DEM |
| Glacier | Season length, reliability | Registry flag | Registry |

### 2.6 Practical factors

| Factor | Why | Measure | Source |
|---|---|---|---|
| Travel time from Munich | A 2.5 h drive needs a better day than a 1 h drive | Precomputed driving time per resort; optional live routing | OpenRouteService / OSRM (§3.6) |
| Road weather on the route | Fresh snow on Fernpass/Kufstein/Brenner adds time and chain risk | Forecast snowfall along the route corridor | Open-Meteo at route points |
| Crowds | Weekends and Bavarian/Austrian school holidays; good-weather weekends are packed | Calendar factor | OpenHolidays API (§3.5) |
| Feedback from your own days | The only way to learn whether the weights match your taste | Stars plus condition chips after a ski day, stored with that day's factor values | App (§9, phase 3) |
| Season / lift status | Not open = score 0 | Registry season dates; later optional resort status feeds | Registry |
| Pass coverage / price | Snow Card Tirol = free marginal cost | Registry | Registry |
| Webcams | Human visual check, not a scored factor | Link-out per resort | Registry (feratel/panomax/resort) |

---

## 3. Data sources (verified where possible)

Legend: ✅ verified endpoint/documentation, ◐ exists but details need a quick
check once the network allows, ✗ not usable.

### 3.1 Weather forecasts

**Open-Meteo** ✅ — primary forecast source.
- Free for non-commercial use, CC BY 4.0, up to 10 000 requests/day, no API key.
- Hourly variables: `temperature_2m`, `precipitation`, `rain`, `snowfall`,
  `snow_depth` (model-based, use only as fallback), `freezing_level_height`,
  `sunshine_duration`, `cloud_cover_low/mid/high`, `visibility`,
  `wind_speed_10m`, `wind_gusts_10m`, `weather_code`. Daily aggregates
  available. 16-day horizon, `past_days` for recent history.
- `elevation=` request parameter downscales to the given altitude, so one
  resort can be queried at base, mid and top elevation.
- Models: `icon_d2` (2 km, 48 h), `icon_eu` (5 days), `icon_seamless`,
  `ecmwf_ifs025`, GeoSphere AROME via the GeoSphere Austria API, and
  `best_match`. Ensemble API available for spread/confidence.
- Attribution "Weather data by Open-Meteo.com" required in the app.

**GeoSphere Austria Data Hub** ✅ — Austrian national service, CC BY 4.0.
- `nwp-v2-1h-2500m` and `nwp-v2-1h-1km`: AROME forecasts (60 h, runs every
  3 h) as grid or point timeseries. Best short-range model for the Austrian
  Alps. (Resource ids changed on 2026-06-16; v1 ids are deprecated.)
- `nowcast-v1-15min-1km`: nowcast; `inca-v1-1h-1km`: hourly analysis.
- Base URL: `https://dataset.api.hub.geosphere.at/v1/`.

**DWD Open Data (ICON-D2)** ◐ — raw GRIB2; only worth it if Open-Meteo is
not enough. Snow depth is only in the D2-EPS ensemble.

**Bergfex** ✗ — no API, scraping is brittle and against typical terms of use.
Keep only as a link-out from the resort page.

### 3.2 Station observations (snow height, temperature, wind, radiation)

**lawinen.report / avalanche.report station feed** ✅ — this is the feed the
"Wetterstationen" page uses. It aggregates EAWS partner stations; the first
live run saw about 1 700 stations, roughly 660 of them with a snow-height
sensor.
- Current: `https://static.avalanche.report/eaws_weather_stations/linea.geojson`
- Snapshots: `https://static.avalanche.report/eaws_weather_stations/{date}/{dateTime}_linea.geojson`
- Properties (verified, SI units): `HS` snow height in m, `HSD_6/24/48/72`
  snow-height differences in m, `TA`/`TA_MIN`/`TA_MAX` air temperature in K,
  `TSS` snow-surface temperature in K, `TD` dew point, `VW`/`VW_MAX` wind and
  gust in m/s, `DW` wind direction, `PSUM_*` precipitation in mm, `RH`, `ISWR`/
  `RSWR` radiation, plus `name`, `altitude`, `operator`, `microRegionID`,
  `date`. The schema lives in the `@albina-euregio/linea` package.
- Each station also carries `dataURLs` with its recent time series: SMET
  files (MeteoIO format, sometimes gzip-compressed without a content-encoding
  header) for the avalanche-service stations, and GeoSphere dataset-API JSON
  for the Tyrolean hydrographic stations. The pipeline reads the last days of
  snow-surface temperature (`TSS`), air temperature and snow height from them;
  in the first live run 40 of 41 resorts had a usable series.
- Open data page: `https://lawinen.report/more/open-data`.

**Land Tirol OGD station CSVs** ✅ — the underlying Tyrolean data, per station
and parameter, e.g.
`https://wiski.tirol.gv.at/lawine/produkte/ogd/GGAL2/GGAL2_HS_latest.csv`
(pattern `{station}/{station}_{param}_latest.csv`; params seen: `HS`, `TP`,
`WR`, …). Listed on data.gv.at as "Wetterstationsdaten Tirol". Ideal for
history because you can fetch each parameter's full recent series.

**LAWIS public API** ◐ — pan-Austrian portal of all Austrian avalanche
services (incl. Salzburg). Swagger at
`https://lawis.at/lawis_api/public/swagger/`. Likely the simplest single
source for Salzburg stations; verify the station endpoints.

**Lawinenwarndienst Salzburg** ◐ — 50+ stations,
`https://lawine.salzburg.at/daten/wetterstationen`; graphs served from
`salzburg.gv.at/lawine/grafiken`. No documented JSON; use LAWIS first.

**Lawinenwarndienst Bayern** ◐ — 20 stations / 36 sensor locations,
10-minute values incl. snow-surface temperature and global radiation.
Website only (`lawinenwarndienst.bayern.de`), no documented API; there is a
measurement archive. Plan: a small scraper with caching, or ask them for a
feed. Bavarian resorts are few, so this can also start manual.

**GeoSphere `tawes-v1-10min`** ✅ — Austrian synoptic stations (temperature,
wind, precipitation, sunshine; snow depth at a subset). Good for valley
temperatures and inversion detection.

**GeoSphere `snowgrid_cl-v2-1d-1km`** ✅ — daily 1 km snow depth and SWE
analysis for Austria (previous day). Fills gaps between stations for the
base-depth check.

Station caveats: snow-height sensors misread during snowfall (snow on the
sensor) and drifting; apply plausibility filters (drop jumps > 30 cm/h,
negative values, stale timestamps > 6 h).

### 3.3 Avalanche bulletins

**EUREGIO bulletin (Tyrol, South Tyrol, Trentino)** ✅ — CAAML v6 JSON:
`https://static.avalanche.report/bulletins/{date}/{date}_EUREGIO_{lang}_CAAMLv6.json`
(danger ratings per micro-region with elevation split, avalanche problems
with aspects/elevations, tendency, text).

**EAWS ratings for all of Europe** ✅ — includes Bavaria (`DE-BY`) and
Salzburg (`AT-05`):
`https://static.avalanche.report/eaws_bulletins/{date}/{date}.ratings.json`,
a JSON object `{"maxDangerRatings": {"DE-BY-10": 2, "DE-BY-10:pm": 3, ...}}`
with warn-level numbers (0 = no rating) per micro-region, optionally split
into `:am`/`:pm`. Only exists for dates with a published bulletin.

**Micro-region polygons** ✅ — `https://regions.avalanches.org/` (eaws-regions,
GeoJSON). Used once to map each resort to its micro-region id(s).

### 3.4 Terrain: elevation bands and aspects

**OpenSkiMap / OpenSkiData** ✅ — daily GeoJSON/GeoPackage of ski areas, runs
and lifts derived from OpenStreetMap, with elevations added from a DEM.
Download at `https://openskidata.org`. Licence ODbL (attribution).

**OpenSkiStats** ✅ — open method (BSD-2 code) that computes per-ski-area
"ski roses" (aspect distribution of downhill runs) and vertical stats from
OpenSkiData. Reuse the method offline to produce one aspect histogram and
elevation profile per resort; store the result in the registry. This answers
your "orientation is hard for a whole resort" concern: it is a one-off
offline computation, not a runtime problem.

**DEM** ✅ — Copernicus GLO-30 (30 m) or SRTM for slope/aspect where
OpenSkiData does not carry it. Also enables a rough "off-piste terrain
above tree line" share per resort.

### 3.5 Calendars

**OpenHolidays API** ✅ — public and school holidays for Germany (Bavaria
subdivision) and Austria (federal states), JSON, free. Also add Dutch and
Baden-Württemberg holidays for the crowd factor if desired.

### 3.6 Routing

**OpenRouteService** (free key) or a public **OSRM** instance ✅ — compute
driving time Munich → resort once and store it. Live traffic is a later
option (Google/TomTom APIs cost money).

For road *weather* no routing service is needed: the pipeline keeps a table of
the real passes used from Munich (Fernpass 1216 m, Gerlospass 1531 m, Pass
Thurn 1274 m, Brenner 1370 m, Arlberg, Radstädter Tauern, Grießenpass and so
on) with their road elevations, and keeps the ones within 22 km of the
straight line to the resort, at most three. Elevation is what decides rain
versus snow, so using the real road height matters more than an exact routed
path. Resorts whose drive crosses no pass (Berchtesgaden, the Bavarian
foothills) are marked as having clear roads rather than unknown ones.

### 3.7 Resort metadata

Static registry maintained in the repo (§7), seeded from the Snow Card Tirol
resort list (`https://www.snowcard.tirol.at/skigebiete-karte`, 90+ resorts)
plus Bavarian and Salzburg resorts, and from OpenSkiData for geometry.

---

## 4. Snow-quality model

Everything is computed per **resort × elevation band × aspect class**, then
aggregated. Bands: base, mid, top (from OpenSkiData). Aspect classes: N
(NW–NE), E, S (SE–SW), W. Computed once per pipeline run from the last ~10
days of station data plus the forecast for the target day.

### 4.1 Derived inputs

- `hn24 / hn48 / hn72`: new snow from station HS differences, clipped at 0,
  with a settling correction of ~10 %/day for fresh snow. Where a dedicated
  new-snow value exists in the feed, prefer it.
- `days_since_snow`: days since last day with hn24 ≥ 10 cm.
- `melt_hours`: hours since last snowfall with air temperature > 0 °C at the
  band elevation (surface temperature ≥ −0.5 °C where a sensor exists).
- `refreeze`: night minimum < −1 °C (or surface temperature < −2 °C) after
  a melt period.
- `cycles`: number of melt→refreeze cycles since last snowfall.
- `sun_load`: sunshine hours since last snowfall × aspect factor × season
  factor. Aspect factor mid-winter: S 1.0, E/W 0.6, N 0.15; from March N
  rises to ~0.4. Season factor scales with sun elevation (December 0.5,
  March 1.0).
- `wind_load`: max gust during and within 24 h after the snowfall.
- `rain_hours`: precipitation hours with freezing level above the band.

### 4.2 Surface state (per band × aspect)

| State | Rule (first match wins) | Freeride value | Piste value |
|---|---|---|---|
| Rain-soaked | `rain_hours` > 1 since last snowfall and no fresh snow on top | 0 | 0.3 |
| Wet / slush | daytime T > +3 °C and no refreeze the night before | 0.2 | 0.4 |
| Fresh powder | hn72 ≥ 15 cm (or hn24 ≥ 10), `melt_hours` = 0, `wind_load` < 35 km/h | 1.0 | 0.9 |
| Wind-affected powder | as above but `wind_load` ≥ 35 km/h | 0.6 (trees/sheltered aspects higher) | 0.8 |
| Settled powder | hn72 < 15 cm, `days_since_snow` ≤ 7, `melt_hours` = 0, `sun_load` low | 0.75 | 0.8 |
| Corn snow window | `cycles` ≥ 3, clear refreeze night, sunny forecast; valid on E/S aspects roughly 09:30–13:00 | 0.7 (with timing hint) | 0.7 |
| Breakable crust | `melt_hours` > 0 or `sun_load` high, then refreeze, `cycles` < 3 | 0.15 | 0.5 |
| Hardpack / old snow | `days_since_snow` > 7, cold, no melt | 0.3 | 0.7 (grooming makes it fine) |

Piste quality is largely decoupled from natural snow once the base is
sufficient, because grooming resets the surface every night. The piste score
therefore uses the state table only lightly and relies on base depth, sun,
visibility and temperature.

### 4.3 Aggregation with the aspect rose

- Freeride: `snow_quality = Σ_aspect share(aspect) × value(band, aspect)`
  using the mid and top bands, plus a bonus if the *best* aspect class has
  ≥ 20 % share (you can go where the snow is good).
- Piste: weighted by band share of piste kilometres.
- Avalanche problems remove aspects: if the bulletin flags e.g. wind slab on
  N–E above 2200 m, those aspect/band cells are capped at 0.2 in freeride
  mode and the reason is shown.

### 4.4 Confidence

Each factor carries a confidence: station distance to the resort and
elevation difference, station data age, forecast lead time (day 0–2 high,
3–5 medium, 6–9 low), and model spread from the ensemble. The UI shows a
score plus a confidence badge, not a false precision.

### 4.5 Calibration

Add a "How was it?" prompt after a ski day (1–5 stars, powder/crust/slush
chips). Store locally with the factor values of that day. After a season this
gives you a personal weight fit and a sanity check on the thresholds above.

---

## 5. Aspects: making orientation tractable

1. Download OpenSkiData runs and ski-area polygons once (or monthly).
2. For each resort polygon, take downhill run segments, compute bearing and
   slope per segment (elevation from OpenSkiData or DEM), weight by length.
3. Store per resort: aspect histogram (8 sectors), elevation histogram,
   top/mid/base elevations, tree-line share, glacier flag.
4. Optionally add named off-piste zones by hand for your favourite resorts
   (polygon, aspect, elevation, hazard notes) — the model already works per
   aspect class, so a hand-drawn zone plugs straight in.

This is offline preprocessing, so the phone never touches a DEM. Implemented
in `pipeline/tools/terrain.py` (first live build: 41 of 41 resorts, e.g.
SkiWelt 426 runs / 234 km, Kühtai 75 runs with 23 % north-facing terrain,
Nordkette mostly south-east to south-west): OpenSkiData already carries elevations on the
run coordinates, so no separate DEM is needed; the downhill direction of every
segment is taken from the elevation difference, and segments flatter than 3 %
are ignored. Matching prefers the smallest OpenSkiMap ski-area polygon that
contains the resort point, so sub-resorts are not swallowed by umbrella areas
such as "Stubai" or "Ski amadé"; `links.openskimap_names` or
`links.openskimap_ids` pin the areas explicitly and `links.radius_km` limits
how far from the resort point runs may lie (needed where two resorts share a
ridge, e.g. Pitztal and Sölden). Roses built from under 5 km of runs are not
used.

---

## 6. Scoring

Score per resort per day, 0–100, two weight sets. Hard blockers first.

**Blockers (score = 0, with reason):** resort closed; base depth below
threshold; freeride mode and danger level ≥ 4; rain forecast for most of the
day at mid elevation.

| Factor | Freeride | Piste |
|---|---|---|
| Fresh snow (hn24/hn72 incl. forecast up to target day) | 25 | 15 |
| Snow quality (§4) | 25 | 15 |
| Avalanche danger (1→1.0, 2→0.8, 3→0.35, 4–5→blocked) | 20 | 0 (info only) |
| Sun / visibility (fog and flat light penalise freeride more) | 10 | 30 |
| Wind (lift closure risk, wind chill) | 5 | 10 |
| Temperature comfort | 5 | 10 |
| Base depth beyond threshold | 0 (blocker only) | 10 |
| Travel time (1 h → 1.0, 2.5 h → 0.4) | 5 | 5 |
| Crowds (holiday/weekend) | 5 | 5 |

Multiply the sum by the confidence factor for display ordering, but show the
raw score and confidence separately. Weights are user-adjustable sliders in
settings; the two presets are starting points.

Pattern detectors shown as badges: **Powder day** (≥ 20 cm in the 48 h
before, sunny and cold on the day), **Bluebird** (≥ 6 h sun, gusts
< 40 km/h), **Inversion** (valley fog, top sunny and warmer), **Corn
morning** (spring cycle satisfied), **Storm skiing** (snowing on the day,
trees available).

---

## 7. Resort registry (example)

```json
{
  "id": "kuehtai",
  "name": "Kühtai",
  "region": "AT-07",
  "micro_regions": ["AT-07-14"],
  "lat": 47.213, "lon": 11.011,
  "elevation": {"base": 2020, "mid": 2300, "top": 2520},
  "aspect_rose": {"N": 0.31, "NE": 0.12, "E": 0.05, "SE": 0.08, "S": 0.14, "SW": 0.10, "W": 0.10, "NW": 0.10},
  "tree_line_share_above": 0.95,
  "glacier": false,
  "passes": ["snowcard_tirol"],
  "season": {"open": "2025-11-28", "close": "2026-04-19"},
  "stations": [
    {"source": "eaws", "id": "…", "name": "Kühtai", "elevation": 2020, "distance_km": 0.8, "weight": 0.7},
    {"source": "eaws", "id": "…", "name": "…", "elevation": 2450, "distance_km": 3.1, "weight": 0.3}
  ],
  "travel_min_from_munich": 150,
  "links": {"resort": "…", "webcams": ["…"], "bergfex": "…"}
}
```

Station mapping rule: up to three stations within ~10 km and ±300 m of the
band elevation, weighted by proximity. The `micro_regions` id comes from the
eaws-regions polygons.

---

## 8. Architecture

Recommended: **scheduled pipeline + static JSON + thin Android client.**

```
GitHub Actions cron (every 3 h in season)
  └─ Python pipeline (reuses/extends the where2ski_py prototype)
       ├─ fetch: Open-Meteo (3 elevations × N resorts), GeoSphere AROME,
       │         station feeds, CAAML bulletins, holidays
       ├─ store: daily station snapshots (history for §4)
       ├─ compute: snow-quality states, scores, badges, confidence
       └─ publish: data/resorts.json, data/latest.json,
                   data/history/{date}.json  → GitHub Pages
Android app (Kotlin, Jetpack Compose)
  ├─ Retrofit fetch of the JSON, Room cache for offline use
  ├─ screens: ranked list per day, day × resort matrix, map (MapLibre or
  │   osmdroid), resort detail with "why" panel and aspect rose
  ├─ settings: mode, weight sliders, passes, max travel time
  └─ WorkManager refresh, home-screen widget "best 3 this weekend",
      local notifications ("Powder alert: 35 cm at Kühtai by Saturday")
```

Why not fully on-device: rate limits multiply by users, history is needed
for the snow-quality model, DEM/aspect work belongs offline, and the Python
prototype already exists in where2ski_py. The pipeline costs nothing on GitHub Actions and
keeps API keys off the phone. If you prefer no backend at all, the same
Python logic can be ported to Kotlin and run on the device against
Open-Meteo and the station feed; only the history part then depends on the
phone having been online regularly.

Kotlin/Compose is recommended over Flutter because there is no iOS
requirement and Android-native background work, widgets and maps are
simpler; Flutter is the alternative if iOS should come later.

### 8.1 Where the pipeline can run (no own server needed)

| Option | Cost | Scheduling | Persistence for history | Caveats |
|---|---|---|---|---|
| **GitHub Actions cron + GitHub Pages** (recommended start) | Free on a public repo: unlimited Actions minutes on standard runners, Pages free. Private repo: 2 000 min/month free (a 3-min job every 3 h ≈ 720 min/month) but Pages then needs a paid plan. | `schedule:` cron, UTC; runs can be delayed by minutes to tens of minutes under load. Publish with `actions/deploy-pages` from an artifact so JSON does not bloat git history. | Commit a small daily snapshot (~100 KB) to a `data/` folder, or re-fetch history from the sources (lawinen.report keeps dated station snapshots, Open-Meteo has `past_days`). | Scheduled workflows on public repos are disabled after 60 days without repository activity; the daily data commit counts as activity, or add a keepalive step. Pages soft limits: 1 GB site, 100 GB/month bandwidth. |
| **Cloudflare Workers cron + KV/R2** | Free: 100 000 requests/day, 3 cron triggers per Worker, KV 1 GB and 1 000 writes/day, R2 10 GB. | Cron triggers, 1-minute minimum, reliable timing. | KV or R2 objects. | Worker runtime is JavaScript/TypeScript (Python Workers still experimental), 10 ms CPU per invocation on the free plan, so heavy computation must be split or moved. |
| **Cloud scheduler + serverless job** (Google Cloud Run Jobs, AWS Lambda) | Effectively free at this volume, but a credit card and billing account are required. | Cloud Scheduler / EventBridge, exact timing. | Object storage or a small database. | More setup and IAM than the task needs. |
| **Own VPS** (e.g. Hetzner) | ~4–5 €/month. | Plain cron. | SQLite, unlimited. | You maintain OS updates, TLS and backups. Only worth it if you later want a real API or ML training. |
| **On-device only** | Free, no infrastructure. | WorkManager periodic fetch (≥ 15 min). | Open-Meteo `past_days` and the dated station snapshots give enough history for the snow model; daily rating data stays local. | Every app open re-fetches ~10 sources and recomputes; no shared cache; harder to debug data problems. Viable as a fallback if the pipeline becomes a burden. |

Decision: start with GitHub Actions + Pages on this public repository. Keep the
pipeline a plain Python package with a `run` entry point so the same code can
move to a Worker, a container or a VPS without changes to the app, which only
ever reads static JSON.


---

## 9. Roadmap

**Phase 1 – replace scraping, ship a usable ranking** (implemented)
- Registry of 41 major resorts with elevations, passes, travel time, links,
  optional season dates.
- Pipeline: Open-Meteo at 3 elevations, EAWS station feed mapping with unit
  conversion, EUREGIO CAAML and EAWS ratings bulletins with micro-region
  lookup, holiday crowd factor, first version of the snow-state heuristics,
  two-mode scoring with blockers, badges and confidence, JSON + status page,
  GitHub Actions cron with Pages publishing and daily station snapshots.
- Android: ranking, day matrix, map, detail page, settings with weight
  sliders, pass filter and travel limit; APK built by CI.
- Known gaps: aspect roses are not yet in the registry (uniform aspect
  factor), resort coordinates and elevations are approximate, Bavarian and
  Salzburg station coverage depends on what the EAWS feed carries.

**Phase 2 – snow quality and safety** (implemented)
- Aspect roses: `pipeline/tools/terrain.py` streams OpenSkiData runs,
  matches them to resorts through the OpenSkiMap ski-area polygons and writes
  `pipeline/data/terrain.json` (8-sector rose, run km, elevation percentiles).
  The `terrain` workflow runs it on demand and commits the result.
- Per-aspect snow states: every day is assessed for all eight sectors with a
  seasonal sun factor (north faces get almost no sun in mid-winter, more from
  March on) and aggregated with the rose: freeride = 70 % weighted mean plus
  30 % of the best sector holding at least 15 % of the terrain; piste = plain
  weighted mean. Aspects named by an avalanche problem in the bulletin are
  capped at 0.2 for freeride.
- Station time series: the EAWS feed links a SMET file per station; the
  pipeline reads the last days of snow-surface temperature (falling back to
  air temperature) and uses them for melt hours, overnight refreeze and
  melt-freeze cycles instead of the model temperature.
- The app shows the rose, the best aspect and the station used.

**Phase 3 – personalisation and comfort** (implemented, except off-piste zones)
- Road conditions on the drive: `pipeline/where2ski_pipeline/sources/route.py`
  keeps the real Alpine road passes used from Munich with their true road
  elevations, matches them to a resort by a corridor around the straight line
  (`links.road_waypoints` pins or clears the list), and fetches them in one
  batched request. Morning snowfall on the worst pass becomes the `roads`
  factor and a per-day report in the app.
- Post-trip ratings: rate a day from the resort page with stars and condition
  chips. The factor values of that day are stored with the rating, so the
  settings screen can correlate each factor with the stars and suggest weights
  that match what you actually enjoyed (from five rated days per mode).
- Alerts and widget: a WorkManager job refreshes every six hours, notifies
  about powder days and days scoring above 75 under your own weights and
  filters (each day announced once), and updates a home-screen widget with the
  best three resorts for the coming weekend.
- Still open: hand-drawn favourite off-piste zones.

---

## 10. Decisions

1. **Decided:** freeride = lift-accessed off-piste within resorts. Touring is of interest but deferred.
2. **Decided:** curated list of major resorts; tiny Snow Card Tirol areas are excluded.
3. **Proposed:** GitHub Actions + Pages pipeline on this public repo (see §8.1); no own server.
4. Open: Kotlin/Compose native vs. Flutter (recommended: Kotlin).
5. Open: sun or powder as tie-breaker (assumed: powder in freeride, sun in piste mode).

---

## 11. Sources

- Open-Meteo: https://open-meteo.com/en/docs , https://github.com/open-meteo/open-meteo
- GeoSphere Austria Data Hub: https://dataset.api.hub.geosphere.at/v1/docs/ , https://github.com/Geosphere-Austria/dataset-api-docs
- lawinen.report stations and open data: https://lawinen.report/weather/stations , https://lawinen.report/more/open-data
- ALBINA website config (station feed and bulletin URL patterns): https://github.com/albina-euregio/albina-website
- Land Tirol station OGD: https://www.data.gv.at/katalog/dataset/land-tirol_wetterstationsdatentirol
- LAWIS public API: https://lawis.at/lawis_api/public/swagger/
- Lawinenwarndienst Salzburg: https://lawine.salzburg.at/daten/wetterstationen
- Lawinenwarndienst Bayern: https://lawinenwarndienst.bayern.de/schnee-wetter-bayern/wetter-schnee-messstationen/
- EAWS regions: https://regions.avalanches.org/
- OpenSkiMap data: https://openskidata.org , https://github.com/russellporter/openskidata-processor
- OpenSkiStats (aspect roses): https://github.com/dhimmel/openskistats
- OpenHolidays API: https://www.openholidaysapi.org/
- Snow Card Tirol resorts: https://www.snowcard.tirol.at/skigebiete-karte
- DWD Open Data ICON-D2: https://www.dwd.de/EN/ourservices/nwp_forecast_data/nwp_forecast_data.html
