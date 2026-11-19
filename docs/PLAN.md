# where2ski – implementation plan, November 2026

This plan follows the review of 16 November 2026. The review compared 65 daily
snapshots of the pipeline with station measurements and with independent
reports, and found that the app's broad picture is right but its two core
promises fail on real data. The plan fixes those first, in an order where each
step can be measured.

Scope: the pipeline (`pipeline/`), the published JSON, and the app screens that
show it. Everything in `docs/CONCEPT.md` stays valid; this document replaces
its roadmap section for the next phase.

## Progress

**First milestone (WP0, WP1, WP2): done on 17 November 2026**, apart from
switching the default branch to `main`, which waits for the owner.

| Item | State | Note |
|---|---|---|
| WP0 record and replay | done | `run --record DIR`, replay with `--offline DIR`; failed requests are replayed too. CI keeps each run's recording for 14 days |
| WP0 development hosts | done | `avalanche.report` added, since the bulletin files redirect there. The weather service's daily limit is shared by the sandbox's exit address, so local live runs can hit 429; CI recordings replace them |
| WP0 `main` as default | pushed 19 Nov | The owner switches the default branch in the repository settings and allows `main` to deploy to the github-pages environment |
| WP1 stale stations | done | Normal reading age is 0.3 to 1 h for every operator; the 6 to 10 Nov freeze would now be flagged |
| WP1 quality control | done | Obergurgl spike rejected (`limit_24h`); GeoSphere's duplicate station records merged |
| WP1 glacier rule | done | No glacier has a depth station within 250 m of its top band yet, so off-piste on glaciers is blocked with "not measured" until WP3 moves the band |
| WP1 missing bulletin | done | Reasons `out_of_season`, `no_rating`, `beyond_bulletin`, `fetch_failed` |
| WP1 opening dates | done | All 41 resorts, with source and `confirmed`; closing dates mostly estimated |
| WP2 archive | done | `data` branch created by CI from the 66 snapshots. `obs` rows carry an extra `run_utc` column to tell the morning and midday sets apart |
| WP2 verification | done | Published as `verification.json` on every run; `verify.yml` weekly and for backtests |

**Baseline reproduced.** From the converted snapshots, lead 0, mid band at
1700 m or higher, 15 Oct to 15 Nov: 5 hits of **46** snow days of 5 cm or
more, with a mean forecast of 1.7 cm against 9.1 cm measured on those days.
The review counted 50 snow days; the four others rested on frozen stations
that repeated an old "new snow" reading for days (for example Feuersang
Messfeld 3, 7.4 cm on three days in a row, 46 to 90 h old). 46 is the
baseline for WP3.

---

## 1. Evidence this plan is built on

| # | Finding | Evidence from the repository's own data |
|---|---|---|
| F1 | Snowfall is under-forecast by a factor of about five | 15 Oct to 15 Nov, resorts with mid band above 1700 m, 619 resort-days. Stations measured 5 cm or more on 50 of them. The same-day forecast said 5 cm or more on 5, and under 1 cm on 29. Mean 1.6 cm forecast against 8.8 cm measured |
| F2 | The precipitation was there; the snow share was wrong | 13 Nov, Hintertux mid band 2600 m: 5.4 mm precipitation at −8.2 °C, snowfall shown 0.1 cm, stations measured 5.9 cm. Same pattern at Pitztal, Stubai, Zugspitze, Kühtai |
| F3 | Fresh snow is labelled crust or corn | 22 Oct, Hintertux: 19.6 cm new at −5.4 °C labelled "crust" with the reason "217 h above 0 °C". 13 Nov, Stubai: 7.8 cm new at −8.5 °C labelled "corn" on all eight aspects. `days_since_snow` was empty in each case |
| F4 | A frozen station feed went unnoticed | Snapshots of 6 to 10 Nov all carry station timestamps of 5 Nov 09:50 UTC. Values were used as current for five days |
| F5 | A sensor spike became a snowfall | 22 Oct, Obergurgl: one of three stations reported 278 cm snow height and 277.5 cm in 24 h. The app used 64.7 cm new snow and 74 cm base |
| F6 | Glacier base depth is a placeholder | Every glacier shows 100 cm. Stations on 16 Nov read 19 cm at Hintertux, 20 at Stubai, 27 at Sölden, 19 at Kaunertal, 72 at Pitztal. The off-piste depth check never triggers, and glaciers scored up to 65 for freeride |
| F7 | Open and closed are wrong in both directions | Zugspitze shown open since 15 Nov, operator plans 27 Nov. KitzSki shown closed, open since 6 Nov on stored snow. Obergurgl, Ischgl, Kühtai, Axamer Lizum and Fieberbrunn all open before the default date of 1 Dec |
| F8 | No avalanche information outside the bulletin season | The avalanche service warned on 12 Nov of wind slab above 2500 m. The app showed nothing and used a neutral factor of 0.7 |
| F9 | Forecast skill beyond day 0 cannot be measured | The daily snapshot stores only the same-day assessment. It is also 139 KB per day, 8.7 MB after 65 days |

Two limits of the evidence, so they are not forgotten:

- "Measured new snow" is the 24 h change of snow height at stations. It
  includes settling, melt on warm ground and wind transport, so it understates
  what fell and is noisy for small amounts.
- A rough re-split of precipitation by daily temperature raised the hits from
  5 to 15 of 50 but also produced 30 forecast snow days with under 2 cm
  measured. Daily aggregates cannot time precipitation against cooling. The
  real fix needs hourly data and a proper test, which is why work package 2
  comes before work package 3.

---

## 2. Principles

1. **Measure before and after.** Each change to the forecast or the snow model
   ships with a number computed from stored data, compared with the baseline
   above.
2. **Honest when blind.** Stale, missing or implausible inputs are shown as
   such and lower the score. They are never replaced by an optimistic default.
3. **Additive JSON.** `latest.json` gains a `schema_version` field. New fields
   are added, old ones kept for one release, so an older app keeps working. The
   app already ignores unknown keys.
4. **Observations beat the model for the past.** Anything before "now" uses
   station data where a trustworthy station exists. The model fills gaps and
   covers the future.
5. **Tunable numbers live in `config.py`** with a comment saying where the
   starting value comes from, so calibration does not mean hunting through
   code.

### WP3 status, 19 November 2026

Experiment 7.1, `verify.py backtest`, 15 Oct to 17 Nov, mid band at 1700 m
or higher, 647 resort-days, 48 days with 5 cm or more measured:

| Query point / snowfall | Hits | Detection | False-alarm ratio | ETS | Mean forecast / measured on snow days |
|---|---|---|---|---|---|
| A registry / service | 14 | 0.29 | 0.46 | 0.21 | 3.8 / 9.0 cm |
| B registry / derived | 26 | 0.54 | 0.61 | 0.25 | 6.0 / 9.0 cm |
| C terrain / service | 13 | 0.27 | 0.32 | 0.22 | 3.4 / 9.0 cm |
| D terrain / derived | 22 | 0.46 | 0.60 | 0.23 | 5.4 / 9.0 cm |

- The derivation is what helps. The terrain query points do not, so the
  pipeline runs B: `SNOWFALL_SOURCE = "derived"`, `QUERY_POINTS = "registry"`.
  The terrain points stay in `terrain.json` for later use.
- Even A finds 14 snow days on this history, against 5 in the live day-0
  archive. The forecast taken at run time misses more than the same model a
  day later, so lead time matters as much as the algorithm. The archive now
  measures lead days 1 to 9 from 17 November on.
- Targets of 7.5 not yet met: detection 54 % (target 60 %), false alarms 61 %
  (target 40 %), forecast on snow days 33 % low (target within 30 %). With
  only 48 snow days from three or four storms, the thresholds are not tuned
  to this sample. Next candidates: the false alarms, by comparing with
  stations that measure precipitation, and the ensemble range of WP7.
- Done from 7.4: derived snowfall for road passes, snow line per hour and
  day, stations matched within 250 m of the band (3 of 26 resorts lose their
  depth station), melt of 1 cm per positive degree-day in the projected base.
  Not possible: the recorded 13 November fixture, because recording started
  on 17 November; unit tests use hand-computed values instead.

### WP4 status, 19 November 2026

The hourly surface model is live (`SURFACE_MODEL = "history"`); the rule
model is still computed and published as `state_rules`.

| Check (docs/PLAN.md 8.4) | Target | Rules | Hourly history |
|---|---|---|---|
| Scenario tests | 6 of 6 | – | 6 of 6 |
| Named snow days (22 Oct, 13 and 14 Nov) | all powder | 1 settled, 4 wind-affected | 4 fresh powder, 1 dust on crust (10 cm on a crust) |
| Crust or corn on 56 measured snow days, 15 Oct to 19 Nov | 0 | 7 | 5 |
| Melt check against snow-surface temperature, daytime hours | 80 % | – | 77 % (303 h, 8 stations) |

Not fully passed, but better than the rules on every check, so it was
switched on; one line in `config.py` switches back. Changes against the
plan's design, each forced by a failing scenario: a cold-content store (a
night's cooling must be repaid before the surface melts, otherwise shaded
slopes melted in mild air), settling towards 35 % of the fallen depth
instead of towards zero, and snow of 1 cm or more on a crust counts as
"dust on crust". `status.melt_check` now splits misses into false and
missed melt hours; that tells whether to tune the long-wave or the
sensible-heat term next. The replay of WP3's derived snowfall alone cut the
rule model's crust-or-corn calls from 41 of 46 snow days (live) to 7 of 56,
so most of F3 was missing snow, not the rules.

---

## 3. Work packages at a glance

| WP | Topic | Fixes | Size | Depends on |
|---|---|---|---|---|
| 0 | Development prerequisites | slow feedback loop | S | – |
| 1 | Honesty fixes: stale data, spikes, glacier base, missing bulletin, opening dates | F4 F5 F6 F8 F7 partly | M | – |
| 2 | Forecast archive and verification tool | F9, yardstick for WP3 and WP4 | M | – |
| 3 | Snowfall per elevation band | F1 F2 | M | WP2 |
| 4 | Snow surface as an hourly history | F3 | L | WP1 WP3 |
| 5 | Lift and piste status | F7 fully | M, with an investigation gate | – |
| 6 | Avalanche coverage outside Tyrol and outside the season | F8 fully | S | WP1 |
| 7 | Confidence from ensembles | false precision | S | WP3 |
| 8 | Past days in the app, and feedback after a ski day | no way to compare a day skied with what was forecast; ratings cannot reach the model | M | WP2 |

Recommended order: 0, 1, 2, 8, 3, 4, then 6, 5, 7. WP1 and WP2 are
independent and can be done in either order. WP8 comes straight after the
archive because feedback collected early in the season is worth the most, and
because seeing past days lets the owner judge every later fix personally. WP5
starts with an investigation that can run in parallel at any time.

**First milestone:** WP0, WP1 and WP2 together. They need no new data source,
they stop the app from showing bad inputs as good ones, and they produce the
numbers every later package is judged by. The milestone is reached when the
verification tool reproduces the review's baseline and the published data
carries no stale, spiked or placeholder value.

Sizes are relative: S is one focused working session, M is two, L is three to
four.

---

## 4. WP0 – Development prerequisites

**Problem.** The development sandbox cannot reach the weather service, the
station feed or the published page. Every pipeline change so far was debugged
through CI logs, and the review could not read the app's own forecast.

**Steps.**

1. Allow these hosts in the development environment so the pipeline runs
   locally: `api.open-meteo.com`, `ensemble-api.open-meteo.com`,
   `static.avalanche.report`, `regions.avalanches.org`, `openholidaysapi.org`,
   `tiles.openskimap.org`, `cczapka.github.io`, `lawinen.at`,
   `wiski.tirol.gv.at`, `dataset.api.hub.geosphere.at`. This needs the
   repository owner's approval.
2. Add `python -m where2ski_pipeline run --record DIR`: writes every raw
   response to `DIR` under the cache key. The existing `--offline DIR` then
   replays it. This gives real-data regression fixtures without hand-building
   them. Change: `Http.get_text` and `Http.get_bytes` in
   `where2ski_pipeline/http.py`, one new CLI flag in `__main__.py`.
3. Create `main` from the current branch and make it the default branch. The
   Pages environment and the scheduled workflows follow the default branch.

**Done when** a full pipeline run works locally and a recorded run replays
offline with identical output.

---

## 5. WP1 – Honesty fixes

Five small changes that stop the app from presenting bad or missing data as
good data. None needs a new source.

### 5.1 Stale station data (F4)

- `sources/stations.py`: parse `Station.time` into an aware datetime and add
  `age_h`. New config `STATION_MAX_AGE_H = 3`. A station older than that keeps
  its metadata but its `hs`, `hn*`, `t_air`, `t_surface`, `gust` are set to
  `None` and `stale = True`.
- `load_stations`: status gains `median_age_h` and `stale_share`. When more
  than half of all stations are stale, add a warning to a new top-level
  `status.warnings` list and print a `::warning::` line so the workflow run
  shows it.
- Fetch the station feed with `ttl_s=0`. Runs are three hours apart, so the
  30 minute cache never helped, and it removes our cache as a suspect for the
  freeze. Log the response's `Last-Modified` header.
- App: a banner on the ranking screen when `status.warnings` is not empty, and
  the station list on the detail page shows the age of each reading.

### 5.2 Implausible station values (F5)

Applied in this order in a new function `quality_control(mapped, yesterday)`:

1. **Hard limits.** Snow height outside 0 to 600 cm, or a 24 h change above
   150 cm, is dropped. Already partly present; tighten.
2. **Agreement.** A 24 h change above 60 cm is dropped unless another mapped
   station reports at least 30 cm.
3. **Continuity.** Compare with the same station's value in yesterday's
   archive row. A jump of more than 60 cm in snow height is dropped unless the
   forecast had at least 20 mm of precipitation.
4. **Bare ground.** Snow height below 60 cm with air temperature above 8 °C
   and zero modelled snow depth is set to 0. This catches sensors reading
   vegetation, as at the Saalbach station in October.
5. **Exclusion list.** `links.exclude_stations` in the registry for stations
   that are known to be unrepresentative.

Then replace the distance-weighted mean in `weighted()` by a robust combiner
`combine()`: the median for three stations; for two, the mean unless they
differ by more than a factor of two, then the lower one. Every dropped value is
listed in the resort's output under `stations[].rejected` with the rule that
fired, so the app can show why.

Tests: the Obergurgl case of 22 October and the Saalbach October readings as
fixtures built from the stored snapshots.

### 5.3 Real base depth, and a real off-piste rule on glaciers (F6)

- `model/snow.py`: delete the glacier floor. `hs` is always the measured or
  modelled value, with its source.
- `model/score.py`, `blockers()`:
  - Piste mode on a glacier is no longer blocked by natural snow depth, because
    the base is ice and the operator decides. Thin cover instead lowers the
    piste snow-quality value and adds the note "thin cover over glacier ice".
  - Freeride mode on a glacier requires `BASE_MIN_FREERIDE_GLACIER = 120` cm,
    measured at a station within 250 m of the top band. Below that the blocker
    reads "too little snow over glacier ice for off-piste: crevasses". Without
    such a measurement the blocker reads "snow depth over the glacier ice is
    not measured". Operator-reported depth is not accepted for this check,
    because it is self-reported and this is a safety rule.
  - Glaciers are not blocked for freeride merely because the bulletin season
    has not started. In an autumn with deep early snow that would hide exactly
    the days worth knowing about. The depth rule above applies, and the
    missing bulletin lowers the score and adds its note through 5.4.
  - Freeride mode elsewhere uses 60 cm where the mid band lies below 2000 m and
    80 cm above, because alpine ground is rock and scree.
- Station choice for the depth check moves from "near the mid band" to "near
  the band being judged", see WP3 step 3.

### 5.4 No bulletin means unknown, not neutral (F8)

- `avalanche_factor()` gets a second argument `reason`:
  - `out_of_season`: no bulletin exists for the region at all. Factor 0.4 and
    the note "No avalanche bulletin is published yet. Off-piste conditions are
    unassessed."
  - `beyond_bulletin`: a bulletin exists for today but the target day is
    further out. Use today's level, plus one if the tendency is increasing,
    with confidence multiplied by 0.8.
  - `fetch_failed`: factor 0.5 and a warning.
- The day object gains `avalanche_note`. The app shows it in place of the
  empty avalanche section.

### 5.5 Opening dates from the operators (F7, first half)

- Replace the two default seasons by a per-resort `season` block for every
  resort, with `open`, `close`, `source` and an optional `limited_until` for
  resorts that start with a few lifts.
- Dates found so far for 2026/27, from operators and press, to be entered:
  KitzSki 6 Nov limited, Sölden winter area open, Obergurgl 19 Nov, Axamer
  Lizum 21 Nov depending on snow, Ischgl 26 Nov, Kühtai 27 Nov, Fieberbrunn
  27 Nov, Zugspitze 27 Nov. The remaining resorts are filled from the
  operators' pages, each with its source link.
- Between `open` and `limited_until` the app shows "limited opening" and the
  piste score is multiplied by 0.6.
- This is a stopgap. WP5 replaces planned dates by actual status.

**Acceptance for WP1.** Replaying the stored snapshots: no resort-day uses a
station value older than three hours; the Obergurgl spike is rejected; no
glacier shows a base depth that is not a measurement; every day without a
bulletin carries a note; the opening dates found so far are reflected.

---

## 6. WP2 – Forecast archive and verification tool

**Problem.** Skill can only be judged for day 0, by hand, and the snapshot
format is too large to keep.

### 6.1 Archive format

Two append-only CSV files per month under `pipeline/data/archive/`.

`forecast-YYYY-MM.csv`, one row per run date, resort and target day:

```
run_date,resort,target,lead,snow_base_cm,snow_mid_cm,snow_top_cm,precip_mm,
snow_line_m,t_mid,sun_h,gust_top,state_mid,new_on_top_cm,hs,hs_source,
score_freeride,score_piste,confidence
```

`obs-YYYY-MM.csv`, one row per run date and mapped station:

```
run_date,resort,station,elevation,obs_time,age_h,hs,hn24,hn48,hn72,t_air,
t_surface,gust,rejected
```

About 45 KB per day for both, against 139 KB now, and it holds all ten lead
days instead of one.

- Written by the first run after 05:00 UTC each day, so the forecast base time
  is consistent. A second observation row set is written by the first run
  after 11:00 UTC for daytime temperatures.
- `run.py`: new function `write_archive()`. The JSON snapshot is no longer
  written. The 65 existing snapshots stay, and
  `tools/snapshots_to_archive.py` converts them into day-0 archive rows so the
  baseline of the review is preserved.
- The archive lives on a separate branch named `data`, so daily data stays
  out of the code history. The pipeline job checks that branch out into a
  second directory, appends the day's rows and pushes it. The verification
  tool and `write_history()` of WP8 read it from the same checkout.
- The `snapshots/` directory stays on the default branch until the converter
  has run and its result is verified, then it is removed from the branch tip.
- To confirm: GitHub disables scheduled workflows after 60 days without
  repository activity, and today's daily snapshot commit on the default branch
  is what prevents that. If pushes to `data` do not count as activity, the
  pipeline also updates a one-line date stamp on the default branch once a
  month.

### 6.2 Verification tool

`pipeline/tools/verify.py` with two commands.

`score` reads the archive, no network needed:

- New snow at 5 cm and 15 cm thresholds, per lead day: hits, misses, false
  alarms, probability of detection, false alarm ratio, bias, mean absolute
  error. Observation is the robust station value of the day after the target.
- Temperature at the mid band against stations within 250 m of that
  elevation.
- Plausibility counters for the snow state: "corn or crust with 5 cm or more
  measured in 24 h", "powder with a measured melting surface".
- Output: a table in the workflow summary and `verification.json` on the
  published page.

`backtest` needs network: refetch the hourly history for a date range with the
`past_days` option of the weather service, which reaches back 92 days, and
recompute a candidate algorithm against the archived observations. It takes
switches for each component so their effect can be separated. WP3 uses this.

Workflow `verify.yml`: weekly and on demand.

**Acceptance for WP2.** `score` reproduces the review's baseline from the
converted snapshots: 5 hits of 50 at lead 0. After three weeks of archive it
reports skill for lead days 1 to 9.

---

## 7. WP3 – Snowfall per elevation band

**Problem (F1, F2).** `fetch_resort_forecast` requests one coordinate, the
registry point, three times with different `elevation` values, and the model
reads the service's `snowfall` variable. Temperature follows the requested
elevation. The snowfall figure does not, and the registry point is usually the
village. The exact mechanism inside the weather service is not confirmed; the
mismatch is.

### 7.1 Experiment first

Using `verify.py backtest` on the events of 21 Oct, 28 Oct, 12 Nov and 13 Nov,
compare four variants against the stations:

| Variant | Query point | Snowfall |
|---|---|---|
| A, today | registry point | service's `snowfall` |
| B | registry point | derived from precipitation |
| C | mountain points per band | service's `snowfall` |
| D | mountain points per band | derived from precipitation |

This shows how much each factor contributes, and whether density matters.
Expected outcome is D. If C alone fixes it, the derivation is still kept
because it gives the snow line and a temperature-dependent density.

### 7.2 Mountain points

- `tools/terrain.py`: for each resort, split the run segments into lower,
  middle and upper third by elevation and write the length-weighted centroid
  and mean elevation of each third to `terrain.json` as
  `points: {base: [lat, lon, ele], mid: […], top: […]}`.
- `registry.py`: `Resort.band_point(band)` returns the terrain point, falling
  back to the registry point and elevation.
- `sources/openmeteo.py`: request the three band points with their own
  coordinates and elevations. Still one request per resort.
- The hand-estimated `elevation` block in the registry becomes a fallback
  only.

### 7.3 Derived snowfall

New module `model/precip.py`, applied to every hourly series after parsing.

1. **Wet-bulb temperature** from band temperature and relative humidity, by
   the Stull approximation. Add `relative_humidity_2m` to `HOURLY_VARS`.
2. **Snow share** `f`: 1 at wet-bulb 0.0 °C or colder, 0 at 1.5 °C or warmer,
   linear between. Where the service delivers `snowfall_height` for the hour,
   use it instead: `f = 1` when the band lies above it, with a 150 m
   transition. Availability of that variable per model is to be confirmed in
   the first run.
3. **Density** of new snow by Hedstrom and Pomeroy:
   `rho = 67.9 + 51.3 * exp(T / 2.6)` kg/m³ for T at or below 0 °C, rising
   linearly to 200 at wet-bulb 1.5 °C. That gives 0.84 cm per mm of water at
   0 °C and 1.33 cm at −5 °C, against the fixed 0.7 used by the service.
4. **Result** per hour: `snow_cm = precip_mm * f * 100 / rho`,
   `rain_mm = precip_mm * (1 - f)`. Stored on the series as `snow_derived`
   and `rain_derived`. The service's value is kept as `snow_api` for
   comparison.
5. **Snow line** per hour: the elevation where the wet-bulb reaches 1 °C,
   from the band temperatures. Daily value is the precipitation-weighted mean.

### 7.4 Where the derived series is used

- `snowfall_cm()`, the 24, 48 and 72 hour sums and `last_snowfall_end()` in
  `model/snow.py`.
- `day_weather()`: `snowfall_cm` becomes per band, plus `snow_line_m`.
- The forward projection of base depth, which also gains melt: subtract
  about 1 cm of depth per positive degree-day at the band. That degree-day
  factor is a starting value to be calibrated against the stations.
- `sources/route.py`: road passes use the same derivation at the pass
  elevation. They have the same weakness today.
- Stations are matched per band: within 10 km and 250 m of the band elevation.
  `STATION_MAX_DZ` drops from 400 to 250 and is applied per band.

### 7.5 App

Detail page: new snow per band and the snow line, for example "above 1400 m".
Ranking card: unchanged, fed by the corrected numbers.

**Tests.** Unit tests for wet-bulb, share, density and snow line against
hand-computed values. A recorded real-data fixture for 13 November at
Hintertux, Pitztal and Stubai.

**Acceptance for WP3**, measured by `verify.py` at lead 0 on 15 Oct to 15 Nov
and on all later data:

| Measure | Baseline | Target |
|---|---|---|
| Detection of days with 5 cm or more | 10 % | 60 % or better |
| False alarm ratio | 17 % of 6 | 40 % or lower |
| Mean forecast on measured snow days | 18 % of measured | within 30 % |

The targets are goals, not guarantees. If they are missed, the ablation of
7.1 says which component to work on next.

---

## 8. WP4 – Snow surface as an hourly history

**Problem (F3).** `assess_day` decides the state from totals over a window
that starts at the last snowfall the model knows of. Station snowfall
overrides the amounts but not that window. The rule list also has no order in
time: snow that falls on top of a crust and a crust that forms on top of snow
look the same.

### 8.1 Design

Replace the rule list by a simulation that walks hour by hour from ten days
ago to the end of the forecast, once per band and aspect. Sixteen passes of
480 hours per resort is negligible work.

State carried from hour to hour:

| Variable | Meaning |
|---|---|
| `new_cm` | settled depth of snow lying on the last firm surface |
| `kind` | powder, wind-packed, moist, wet, crust, rain crust, corn frozen, corn soft, hard |
| `under` | what lies beneath `new_cm`: firm, crust, or ice |
| `wet` | liquid water index of the surface, 0 to 1 |
| `cycles` | melt and refreeze cycles since the last snowfall of 10 cm or more |
| `loaded` | wind has added snow to this aspect |

Inputs per hour, per band:

- New snow and rain from WP3. For past hours, measured increments from the
  station series replace the model where a trusted station exists.
- Surface temperature: the measured snow-surface temperature of a station
  within 250 m of the band, else an estimate from the energy terms below.
- Energy at the surface for the aspect:
  `Q = (1 - albedo) * SW_slope + 15 * T_air - L` in W/m², where `SW_slope` is
  direct sunlight projected onto a 25° slope of that aspect from solar
  position, plus diffuse light; albedo falls from 0.85 for new snow to 0.6
  for old; `L` is 60 W/m² under clear sky, falling to 12 under full cloud. Add
  `direct_normal_irradiance`, `diffuse_radiation` and `wind_direction_10m` to
  `HOURLY_VARS`. This replaces the fixed aspect table and the monthly season
  factor.
- Gusts and wind direction at the top band.

Transitions each hour, in this order:

1. **Snowfall.** `new_cm` grows. Cold snowfall of 3 cm or more makes the
   surface powder; snowfall at positive wet-bulb makes it moist. What was
   there before becomes `under`.
2. **Rain.** Surface becomes wet and is marked as rained on.
3. **Melt.** When `Q` is positive and the surface is at 0 °C, `wet` rises
   with the melted water. Powder turns moist above 0.15 and wet above 0.5.
   Frozen corn turns soft between 0.1 and 0.5, then to slush.
4. **Refreeze.** After two hours of negative `Q` with a wet surface: one more
   cycle; the surface becomes rain crust if it was rained on, corn frozen at
   three or more cycles, otherwise crust.
5. **Wind.** Gusts of 45 km/h or more over cold powder: aspects facing the
   wind lose half of `new_cm` and become wind-packed; aspects in the lee gain
   30 % and are marked `loaded`.
6. **Settling.** `new_cm` decays with a time constant of 72 hours at −5 °C or
   colder and 36 hours near 0 °C.

### 8.2 From state to skiing value

Evaluated at 10:00, 12:00 and 14:00 of the target day. The day's value is the
best of the three, and the hour is reported, because corn and spring powder
are a matter of timing.

| Surface | Freeride | Piste |
|---|---|---|
| Powder on a firm base, by depth | 0.5 at 5 cm rising to 1.0 at 25 cm | 0.9 |
| Powder under 12 cm on crust or ice | 0.25, "dust on crust" | 0.8 |
| Wind-packed | 0.5 | 0.85 |
| Moist new snow | 0.45 | 0.6 |
| Corn soft | 0.75 | 0.7 |
| Corn frozen, crust | 0.3, 0.15 | 0.6 |
| Wet, slush | 0.2 | 0.4 |
| Rain crust | 0.05 | 0.4 |
| Hard old snow | 0.3 | 0.7 |

Aggregation over aspects with the terrain rose stays as it is. Aggregation
over bands is new: mid and top weighted by their share of run length, which
`tools/terrain.py` adds to `terrain.json` as `band_share`.

### 8.3 Code

- New `model/surface.py` with `simulate(band_series, top_series, aspect,
  history, start, end) -> list[HourState]` and `value(state, mode)`.
- New `model/solar.py`: solar elevation and azimuth from date, hour and
  latitude; projection onto a slope.
- `assess_resort_day` calls the simulation once per resort and reads the
  hours it needs, instead of calling `assess_day` eight times per day.
- `SnowAssessment` keeps its public fields and gains `new_on_top_cm`,
  `under`, `best_hour` and `loaded_aspects`. `melt_hours` and `sun_load` are
  kept for one release and then removed.
- `assess_day` stays until the new model passes acceptance, behind a config
  switch `SURFACE_MODEL = "rules" | "history"`, so both can be scored side by
  side on the same days.

### 8.4 Tests and acceptance

- Scenario tests, synthetic: cold storm gives powder; storm then warm sun
  gives crust on south and powder on north; 3 cm on crust gives dust on crust
  and 20 cm on crust gives powder; five clear spring days give a corn window
  in the late morning; rain then frost gives rain crust; strong north-west
  wind packs north-west and loads south-east.
- Real cases recorded with WP0: 22 Oct Hintertux and Stubai, 13 Nov Stubai
  and Pitztal, 14 Nov Hintertux. Each must come out as powder.
- Melt check against measurement: on stations that report snow-surface
  temperature, the estimated energy sign must agree with "surface at 0 °C" in
  at least 80 % of daytime hours, evaluated for flat ground.
- Plausibility counters from WP2: "corn or crust with 5 cm or more measured"
  drops to zero.
- Later, and not a gate: agreement with the user's own trip ratings.

---

## 9. WP5 – Lift and piste status

**Problem (F7).** Planned dates say nothing about what actually runs. Stored
snow, snowmaking, wind and maintenance decide.

### 9.1 Investigation, with a gate

Produce a table for all 41 resorts: where the operator publishes lift and
piste status, whether that page is backed by a machine-readable feed, and what
the terms of use say. Known starting points: Intermaps runs the status pages
of most Tyrolean resorts; the joint page of the five Tyrolean glaciers lists
open status, snow depth and last snowfall; Liftie is an open-source collection
of status scrapers that can be self-hosted.

Then ask for permission where a feed exists but no terms are published. The
request is drafted as part of this package and sent by the owner from his own
address, since it is his project and his name. It states the purpose, the
request rate of once per three hours, and that the app is personal and
non-commercial. Until an answer arrives, only sources whose published terms
allow automated reading are used.

**Gate.** If a permitted source covers at least 70 % of the resorts, build the
adapters below. If not, keep WP1's planned dates, add a manual override file
in the repository, and let the app user mark a resort as open or closed.

### 9.2 Adapters

- `sources/liftstatus.py` with one small provider class per source and a
  common result: `lifts_open`, `lifts_total`, `pistes_open_km`,
  `pistes_total_km`, `snow_base_cm`, `snow_top_cm`, `last_snowfall`,
  `updated`. Registry field `links.status` names provider and resort key.
- Fetched once per run, cached for three hours, and subject to the same age
  rule as stations.
- `score.py`: new factor `open_share`, the share of lifts running, 1.0 from
  60 % upward and falling linearly to 0.3 at 10 %. Zero lifts is a blocker.
  It replaces the season gate when status is available.
- Operator-reported snow depth is shown next to the station value and never
  used for scoring. It is self-reported.

### 9.3 App

Ranking card: "22 of 31 lifts". Detail page: status block with its age.
Filter: "open now".

**Acceptance.** For the resorts with a source, the open or closed state
matches the operator's page on ten spot-checked days.

---

## 10. WP6 – Avalanche coverage

- **Bavaria and Salzburg.** The host that serves the Tyrolean bulletin also
  publishes per-region files named `{date}-DE-BY.json` and
  `{date}-AT-05.json`, next to the ratings files the pipeline reads now.
  Directory listings of earlier seasons show them. `config.BULLETIN_SOURCES`
  gets them as the first choice, parsed by the existing `parse_caaml`, with
  the ratings file as fallback. This brings avalanche problems, aspects and
  elevations to resorts outside Tyrol, so aspect capping works there too. The
  file format is to be confirmed when the first bulletin of the season
  appears.
- **Before the season.** Fetch the avalanche service's blog list and attach
  the newest entry's title, date and link to `avalanche_note` from WP1.
  Whether the list endpoint is public is to be confirmed.
- **Beyond tomorrow.** Covered by the `beyond_bulletin` rule in WP1.

**Acceptance.** On the first day with a Bavarian bulletin, a Bavarian resort
shows avalanche problems with aspects.

---

## 11. WP7 – Confidence from ensembles

- `sources/ensemble.py`: one request per resort to the weather service's
  ensemble interface for precipitation and temperature at the mid point. The
  short-range ensemble has 20 members at 2 km for two days; the medium-range
  one has 40 members for seven and a half days. Exact model keys are to be
  confirmed.
- Apply WP3's derivation to each member. Per target day: 10th, 50th and 90th
  percentile of new snow and the probability of 10 cm or more.
- `score.confidence()` uses the spread in place of the fixed lead-time table.
- App: new snow shown as a range, for example "10 to 25 cm", and a
  probability on the alert.

**Acceptance.** Over a month of archive, measured new snow falls inside the
10 to 90 range on 70 to 90 % of days.

---

## 12. WP8 – Past days in the app, and feedback after a ski day

**Problem.** Two gaps in the app as built:

- The detail screen offers only the days of the current forecast. A day can
  be rated until midnight and is gone the next morning. There is no way to
  look at a day already skied and compare it with what was forecast.
- A rating is stars plus free chips, stored only on the phone, and used only
  to suggest factor weights. It says nothing about where on the mountain the
  snow was found, and it never reaches the snow model.

Stations measure depth and temperature. Nobody measures "is it crust". The
skier's own report is the only ground truth the snow-surface model of WP4 can
ever get, so this package is worth more than its size suggests.

### 12.1 History published by the pipeline

Built from the archive of WP2, so it depends on that package.

- `run.py`, new `write_history()`: one file per resort on the published page,
  `history/{resort}.json`, covering the season so far. Per past date:

```json
{
  "date": "2026-11-13",
  "forecast": {
    "3": {"score_freeride": 41, "score_piste": 58, "snow_mid_cm": 1, "snow_top_cm": 2,
          "state": "crust", "sun_h": 4.5, "gust_top": 60, "t_mid": -6},
    "1": {"…": "same fields, forecast made the day before"},
    "0": {"…": "same fields, forecast made that morning"}
  },
  "measured": {"new_snow_cm": 9.0, "base_cm": 22, "t_min": -9.1, "t_max": -4.2,
               "gust_max": 57, "surface_melting_h": 0, "stations": 3},
  "analysis": {"state": "powder", "new_on_top_cm": 12, "sun_h": 5.0}
}
```

- `forecast` holds what the app said three days before, the day before and
  that morning. Lead days kept are a config list, `HISTORY_LEADS = [0, 1, 3]`.
- `measured` comes from the stations, after the quality checks of WP1: new
  snow by the following morning, base depth, temperature range, strongest
  gust, and hours with a melting surface where a station measures it.
- `analysis` is the pipeline's own second opinion, computed the day after with
  the measurements in hand. With WP4 it is simply the surface history read at
  yesterday noon. It is stored in the archive as lead −1. Sunshine has no
  station measurement, so it is the weather model's short-range value and is
  labelled as such in the app.
- Size: about 50 KB per resort and season. The app fetches a file only when a
  resort's history is opened.
- Backfill: the 65 stored snapshots give the same-morning forecast and the
  measurements back to 13 September. Forecasts from earlier lead days exist
  from the day the archive starts.

### 12.2 Past days in the app

- Resort detail screen: a "Past days" button opens `HistoryScreen`. Newest
  first, one row per day: date, the score forecast the day before, measured
  new snow, and the owner's stars if the day was rated.
- Tapping a day opens `DayCompareScreen`:

| | 3 days before | Day before | That morning | Measured |
|---|---|---|---|---|
| New snow | 1 cm | 2 cm | 2 cm | 9 cm |
| Surface | crust | crust | corn | powder, by analysis |
| Base | 12 cm | 12 cm | 13 cm | 22 cm |
| Sun | 4.5 h | 5 h | 5 h | 5 h, model |
| Gusts at top | 60 | 55 | 57 | 57 km/h |
| Score | 41 | 46 | 58 | – |

  Cells that disagree with the measured column beyond a tolerance are
  highlighted. Above the table one generated sentence gives the verdict, for
  example "New snow under-forecast by 7 cm. Wind and sun matched." The owner's
  own report, if there is one, is shown as a further column.
- **Rating works here.** "Rate this day" on a past day uses the forecast of
  that morning for the factor values. This removes the midnight limit.
- A "My days" list in settings: every rated day with forecast score, stars,
  and whether the surface report agreed.
- Code: `Repository.history(resortId)` with a file cache, new models
  `HistoryDay`, `HistoryForecast`, `Measured`, two new screens, one new route
  in `App.kt`. A unit test decodes a sample file and checks the verdict
  sentence.

### 12.3 A feedback form that matches what the model predicts

The form replaces the free chips. It is meant to take half a minute on the
last lift or in the evening. Every question is optional.

1. **The day overall**: one to five stars. This is taste, and feeds the
   weights as today.
2. **Snow where you skied**, up to three entries, each with:
   - surface: powder, wind-packed, heavy and moist, breakable crust, firn or
     corn, hard or icy, slush. The same list as the surface kinds of WP4.
   - fresh snow on top: none, about 5, 10, 20, or 30 cm and more
   - facing: north, east, south, west, or mixed
   - height: lower, middle, or upper part of the resort
   - on piste or off piste
3. **Visibility**: clear, flat light, fog. **Wind**: calm, windy, lifts
   closed by wind.
4. **Crowds**: empty, normal, packed. **Lifts**: all, most, few.
5. A free note.

`TripRating` gains `observations`, `visibility`, `wind`, `crowd`, `lifts` and
`note`, all with defaults, so existing ratings still load.

**Being asked at the right moment.** A forecast day gets a "Going" switch.
A planned day is stored on the phone, and at 18:00 that evening a
notification asks "How was Sölden?" and opens the form. A planned day also
triggers a notification when its score changes by 15 points or more
beforehand. No location permission is needed.

### 12.4 What the feedback is used for

Three uses, in rising order of effort.

1. **On the phone, at once.** The comparison screen shows the report next to
   forecast and analysis, per entry: "South side, middle: you found crust, the
   app said crust." Settings show running agreement, for example "surface
   matched on 7 of 10 reports, fresh snow within 5 cm on 6 of 10".
2. **Personal weights.** The existing suggestion from stars stays. It gains
   nothing from the new questions directly, but the stars become easier to
   interpret once a bad day can be traced to a wrong forecast instead of a
   wrong weight.
3. **The model itself.** A "Share feedback" button exports all reports as one
   JSON file through the Android share sheet. A new command
   `verify.py feedback FILE` compares each report with the archive: a table of
   reported against forecast surface kind, the error of fresh snow depth, and
   a list of every disagreeing day. Each disagreement becomes two things: a
   recorded regression case, using the record and replay of WP0, and a data
   point for tuning the thresholds of WP4, such as the depth at which new snow
   hides a crust.

What this cannot do: with one skier and perhaps 25 days a season, feedback
will not retrain a model statistically. It finds systematic errors and pins
them down as tests, which is how the review of November 2026 worked, only
with far better evidence.

**Getting reports off the phone.** The repository is public, so anything
stored in it shows where and when the owner skied. Reports therefore stay on
the phone, and leave it only by the export button. The owner exports a few
times per season and commits the file to a private repository of his own.
`verify.py feedback` takes the file path as an argument and never copies
report content into the public repository; only the resulting thresholds and
anonymous test inputs are committed there.

Automatic sync is deferred. It is worth revisiting when the form is in
regular use or a second person uses the app. The two candidates, in order of
preference: the app opens a pre-filled issue in the private repository, which
needs one tap and no secret on the phone; or the app commits directly with an
access token limited to that one repository.

### 12.5 Tests and acceptance

- Unit tests for decoding history, the verdict sentence, the extended rating
  with old and new files, and the export format.
- `verify.py feedback` on a hand-made file with one agreeing and one
  disagreeing report.

**Acceptance.** A day skied a week ago can be opened, compared and rated. An
exported file with ten reports produces the agreement table. The form can be
completed in under a minute; the owner is the judge of that.

---

## 13. App changes in one place

| Change | From |
|---|---|
| Banner when data is stale or a source failed | WP1 |
| Station readings with their age, rejected values with the reason | WP1 |
| Real base depth with source; glacier off-piste blocker text | WP1 |
| Avalanche note in place of the empty section | WP1, WP6 |
| "Limited opening" label | WP1 |
| New snow per band, snow line | WP3 |
| Surface with what lies beneath, best hour of the day, wind-loaded aspects | WP4 |
| Lifts open, "open now" filter | WP5 |
| New snow as a range, probability on alerts | WP7 |
| Forecast quality card from `verification.json` | WP2 |
| Past days per resort with a forecast against measurement comparison | WP8 |
| Rating of past days; structured feedback form; "Going" switch with an evening reminder | WP8 |
| "My days" list, agreement statistics, feedback export | WP8 |

`Models.kt` gains the fields with defaults, so one app build reads both old
and new data. Each package updates `ScoringTest` with a sample of the new
JSON.

---

## 14. Risks and open questions

| Risk | Mitigation |
|---|---|
| The weather service's handling of elevation is undocumented and may change | Derive snowfall ourselves; keep the service value only for comparison |
| Station "new snow" is a noisy truth | Robust combination, two thresholds, compare raw and settled forecast, report sample sizes |
| Lift status has no open interface | Investigation gate in WP5 with a fallback that still improves on today |
| The energy terms in WP4 have several tunable numbers | Calibrate against measured snow-surface temperature before trusting them; keep the old rules switchable until then |
| More requests per run | Today 42 requests per run to the weather service, about 340 per day, against its fair-use limit of 10 000. WP7 adds 41 per run |
| Repository growth from daily data | CSV archive at a third of today's size; optional `data` branch |
| Feedback reveals where and when the owner skied | Reports stay on the phone by default; export goes to a private repository |
| A long form does not get filled in | Every question optional; stars alone remain a valid rating; an evening reminder for planned days |

### Decisions taken

Agreed with the owner on 16 November 2026, following the recommendations of
this plan.

| Topic | Decision | Who acts, and when |
|---|---|---|
| Order of work | 0, 1, 2, 8, 3, 4, 6, 5, 7. First milestone is WP0 with WP1 and WP2 | – |
| Development hosts | The hosts listed in WP0 are allowed in the development environment | An approval prompt is raised at the start of WP0; the owner confirms it |
| Forecast archive | On a separate `data` branch | Set up in WP2 |
| Status feeds | Ask for permission; use only sources whose terms allow it until then | Request drafted in WP5, sent by the owner |
| Freeride on glaciers | 120 cm measured near the top band, as a starting value. No blanket block before the bulletin season. No measurement means blocked | WP1 |
| Default branch | Create `main` from the current branch and make it the default | Branch pushed on the owner's go-ahead; the default is switched by the owner in the repository settings |
| Feedback leaving the phone | Export by hand into a private repository. Automatic sync deferred | WP8; the owner creates the private repository |

Decided by the owner on 19 November 2026:

| Topic | Decision |
|---|---|
| Feedback after a ski day (WP8, 12.3 to 12.5) | Dropped. The owner gives feedback in the development sessions, which tune the parameters directly. Past days in the app (12.1, 12.2) stay in the plan |
| Repository visibility | The owner may make the repository private. On a free GitHub plan that switches off GitHub Pages, which serves the app's data, and limits Actions minutes; to be checked before switching |
| Next packages | WP3, then WP4, WP6, WP5, WP7 |

### Still to confirm during implementation

These are technical unknowns, not decisions. Each is checked by the package
that depends on it, and each has a fallback already described there.

| Unknown | Checked in | Fallback |
|---|---|---|
| Whether the weather service delivers a snow-line variable per model | WP3 | Wet-bulb estimate from band temperatures |
| Which of query point, phase split and density explains the snowfall miss | WP3, experiment 7.1 | The ablation table says where to work next |
| Format of the per-region bulletin files for Bavaria and Salzburg | WP6, on the first bulletin of the season | Ratings file, as today |
| Whether the avalanche service's blog list is publicly readable | WP6 | Static note with a link to the blog |
| Exact model keys of the ensemble interface | WP7 | Lead-time table, as today |
| Whether pushes to `data` keep scheduled workflows alive | WP2 | Monthly date stamp on the default branch |
| Whether a permitted status source covers 70 % of resorts | WP5 | Planned dates, a manual override file, and the app user's own marking |

---

## 15. Not in this plan

Kept for later, in rough order of value: a second weather model from
GeoSphere as a cross-check, daily gridded snow depth from GeoSphere to judge
stations, crowd estimates beyond the calendar, hand-drawn off-piste zones,
satellite snow cover for the lower snow line, and instrumented tests of the
app on a device.
