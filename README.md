# where2ski

[![pipeline](https://github.com/cczapka/where2ski/actions/workflows/pipeline.yml/badge.svg)](https://github.com/cczapka/where2ski/actions/workflows/pipeline.yml)
[![android](https://github.com/cczapka/where2ski/actions/workflows/android.yml/badge.svg)](https://github.com/cczapka/where2ski/actions/workflows/android.yml)

An Android app that suggests **where and when** to go skiing from Munich:
Bavarian Alps, Tyrol (Snow Card Tirol) and the Salzburg area, with a focus on
free skiing but useful for piste days too.

It combines weather forecasts, station observations of snow height and
temperature, avalanche bulletins and per-resort terrain data (elevation
bands, aspects) into a snow-quality model and a ranked, explainable score per
resort and day.

## Status

Phase 1 in progress. The design, data sources, scoring and roadmap are
documented in [docs/CONCEPT.md](docs/CONCEPT.md).

The earlier Python command-line prototype (Bergfex forecast ranking by sun
hours) lives in [where2ski_py](https://github.com/cczapka/where2ski_py).

## Structure

```
pipeline/   Python data pipeline: fetch open data, snow model, scoring, JSON output
android/    Android app (Kotlin, Jetpack Compose) that reads the published JSON
docs/       Concept and design notes
.github/    Workflows: pipeline (cron, publishes to GitHub Pages) and android (APK build)
```

## Pipeline

```sh
cd pipeline
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest              # unit tests, no network needed
python -m where2ski_pipeline run --out out -v   # live run, writes out/latest.json
```

`latest.json` holds, per resort and day, the factor values, both scores,
blockers, badges, the snow assessment, weather summary and avalanche info.
`resorts.json` is the static registry (`pipeline/data/resorts.json`).
The GitHub Actions workflow runs the pipeline every three hours in season and
publishes the output to GitHub Pages at
`https://cczapka.github.io/where2ski/` (`latest.json`, `resorts.json`, and a
small status page). Once a day it also commits a station snapshot to
`pipeline/data/snapshots/` as history for the snow model.

## Android app

Kotlin with Jetpack Compose. It downloads `latest.json`, caches it, and lets
you switch between Freeride and Piste mode, adjust factor weights with sliders,
filter by pass and travel time, and browse a ranking, a day-by-resort matrix, a
map and a detail page per resort. The `android` workflow builds a debug APK on
every push and attaches it to the workflow run.

Open `android/` in Android Studio, or build with `./gradlew :app:assembleDebug`.

To try it without a build: open the latest successful run of the `android`
workflow on GitHub, download the `where2ski-debug-apk` artifact, unzip it and
install the APK on the phone (installation from unknown sources must be
allowed once). The debug build is unsigned for stores but fine for personal use.

## Data sources and attribution

Weather data by [Open-Meteo.com](https://open-meteo.com) (CC BY 4.0). Station
data from the EAWS partner services via lawinen.report. Avalanche bulletins
from avalanche.report (EUREGIO) and EAWS. Warning regions from
[eaws-regions](https://regions.avalanches.org). Holidays from the
[OpenHolidays API](https://www.openholidaysapi.org).
