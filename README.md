# where2ski

An Android app that suggests **where and when** to go skiing from Munich:
Bavarian Alps, Tyrol (Snow Card Tirol) and the Salzburg area, with a focus on
free skiing but useful for piste days too.

It combines weather forecasts, station observations of snow height and
temperature, avalanche bulletins and per-resort terrain data (elevation
bands, aspects) into a snow-quality model and a ranked, explainable score per
resort and day.

## Status

Concept phase. The design, data sources, scoring and roadmap are documented in
[docs/CONCEPT.md](docs/CONCEPT.md).

The earlier Python command-line prototype (Bergfex forecast ranking by sun
hours) lives in [where2ski_py](https://github.com/cczapka/where2ski_py).

## Planned structure

```
pipeline/   Python data pipeline (fetch, snow-quality model, scoring, JSON publishing)
app/        Android app (Kotlin, Jetpack Compose)
docs/       Concept and design notes
```
