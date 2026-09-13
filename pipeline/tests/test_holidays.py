from datetime import date

from where2ski_pipeline.sources.holidays import _dates, crowd_factor


def test_dates_expand_ranges():
    ds = _dates([{"startDate": "2026-02-16", "endDate": "2026-02-18"}, {"startDate": "2026-03-01"}])
    assert ds == {date(2026, 2, 16), date(2026, 2, 17), date(2026, 2, 18), date(2026, 3, 1)}


def test_crowd_factor():
    hol = {"school": {date(2026, 2, 16), date(2026, 2, 21)}, "public": {date(2026, 1, 6)}}
    assert crowd_factor(date(2026, 1, 14), hol) == 1.0  # Wednesday
    assert crowd_factor(date(2026, 1, 17), hol) == 0.7  # Saturday
    assert crowd_factor(date(2026, 2, 21), hol) == 0.5  # Saturday in school holidays
    assert crowd_factor(date(2026, 2, 16), hol) == 0.8  # Monday in school holidays
    assert crowd_factor(date(2026, 1, 6), hol) == 0.6  # public holiday on a Tuesday
