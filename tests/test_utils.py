from datetime import date

from app.utils import dump_categories, level_for_points, load_categories, normalize_hhmm, week_key_for


def test_normalize_hhmm():
    assert normalize_hhmm("08:30") == "08:30"
    assert normalize_hhmm("напомни в 9") == "09:00"
    assert normalize_hhmm("25:00") is None


def test_categories_roundtrip():
    raw = dump_categories(["health", "mind", "health"])
    assert load_categories(raw) == ["health", "mind"]


def test_level_for_points():
    level, current, next_, title = level_for_points(130)
    assert level >= 3
    assert current <= 130 < next_
    assert title


def test_week_key():
    assert week_key_for(date(2026, 4, 27)).startswith("2026-W")
