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
| Resorts | Curated registry (see §7). Start with ~40: the Snow Card Tirol resorts you actually reach in ≤ 2.5 h plus Bavarian and Salzburg ones. |
| Modes | **Freeride** and **Piste**. Same data, different weights and blockers. |
| Horizon | Today + 9 days (matches the Python prototype); confidence decays with lead time. |
| Passes | Each resort carries a `passes` list (`snowcard_tirol`, `ski_amade`, …). "Snow Card Tirol only" is a filter, not a hard rule. |
| Output | A ranked list per day, a day × resort matrix ("when"), a map, and a resort detail page with the reasoning ("why"). |

Free skiing is interpreted as lift-accessed off-piste within resorts. Ski
touring is out of scope for now but the same model would apply.

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
"Wetterstationen" page uses. It aggregates EAWS partner stations (Tyrol,
South Tyrol, Trentino, Carinthia and others).
- Current: `https://static.avalanche.report/eaws_weather_stations/linea.geojson`
- Snapshots: `https://static.avalanche.report/eaws_weather_stations/{date}/{dateTime}_linea.geojson`
- Properties per station (to confirm on first fetch): snow height, 24/48/72 h
  differences, air temperature, snow-surface temperature, wind speed/direction,
  elevation, operator, timestamp.
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
`https://static.avalanche.report/eaws_bulletins/{date}/{date}{region}.ratings.json`.

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

This is offline preprocessing, so the phone never touches a DEM.

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

---

## 9. Roadmap

**Phase 1 – replace scraping, ship a usable ranking (2–3 weekends)**
- Registry for ~40 resorts with elevations, passes, travel time, links.
- Pipeline: Open-Meteo at 3 elevations, station feed mapping, base-depth and
  fresh-snow calculation, piste/freeride scores without the full quality
  model, JSON publishing.
- Android: list, matrix, map, detail page, settings.

**Phase 2 – snow quality and safety**
- Daily station history, snow-state machine (§4), aspect roses from
  OpenSkiData, CAAML bulletins with problem-aspect capping, confidence.
- Badges, "why" panel.

**Phase 3 – personalisation and comfort**
- Post-trip rating and weight calibration, notifications and widget,
  holiday crowd factor, route snowfall, LWD Bayern and Salzburg station
  coverage completed, hand-drawn favourite off-piste zones.

---

## 10. Decisions to take

1. Freeride = lift-accessed off-piste only, or also touring? (assumed: off-piste only)
2. Initial resort list: curated ~40 or the full Snow Card Tirol list? (assumed: curated)
3. Backend via GitHub Actions + Pages (data is public anyway) vs. everything on the phone? (recommended: pipeline)
4. Kotlin/Compose native vs. Flutter? (recommended: Kotlin)
5. Default weights: is sun or powder the tie-breaker for you? (assumed: powder in freeride, sun in piste mode)

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
