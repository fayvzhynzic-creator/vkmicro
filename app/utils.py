from __future__ import annotations

import json
import random
import re
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config import settings
from app.content import WEEKLY_THEMES


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def safe_zone(tz_name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(tz_name or settings.default_timezone)
    except ZoneInfoNotFoundError:
        return ZoneInfo(settings.default_timezone)


def local_now(tz_name: str | None) -> datetime:
    return utc_now().astimezone(safe_zone(tz_name))


def local_today(tz_name: str | None) -> date:
    return local_now(tz_name).date()


def parse_hhmm(value: str, fallback: str = "09:00") -> time:
    try:
        hours, minutes = value.split(":", 1)
        return time(hour=int(hours), minute=int(minutes))
    except Exception:
        hours, minutes = fallback.split(":", 1)
        return time(hour=int(hours), minute=int(minutes))


def normalize_hhmm(text: str) -> str | None:
    explicit = re.search(r"(?:^|\D)(\d{1,2})[:.](\d{2})(?:\D|$)", text)
    if explicit:
        hour = int(explicit.group(1))
        minute = int(explicit.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
        return None

    spaced = re.search(r"(?:^|\D)([01]?\d|2[0-3])\s+([0-5]\d)(?:\D|$)", text)
    if spaced:
        return f"{int(spaced.group(1)):02d}:{int(spaced.group(2)):02d}"

    hour_only = re.search(r"(?:^|\D)([01]?\d|2[0-3])(?:\D|$)", text)
    if hour_only:
        return f"{int(hour_only.group(1)):02d}:00"
    return None


def week_key_for(day: date) -> str:
    iso = day.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def sanitize_name(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw.strip())
    name = re.sub(r"[\r\n\t]", " ", name)
    if len(name) > 40:
        name = name[:40].rstrip()
    if not name:
        return "Герой"
    return name


def load_categories(raw: str | None) -> list[str]:
    default = ["health", "mind", "order", "social", "creativity"]
    if not raw:
        return default
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            categories = [str(x) for x in data if isinstance(x, str)]
            return categories or default
    except json.JSONDecodeError:
        pass
    return default


def dump_categories(categories: list[str]) -> str:
    return json.dumps(sorted(set(categories)), ensure_ascii=False)


def level_for_points(points: int) -> tuple[int, int, int, str]:
    # Returns current level, points at current level threshold, next threshold, title.
    thresholds = [0, 50, 120, 220, 350, 520, 750, 1000, 1350, 1800]
    titles = [
        "Новичок микродел",
        "Разогрев",
        "Стабильный",
        "Серийщик",
        "Мастер галочек",
        "Антипрокрастинатор",
        "Легенда маленьких шагов",
        "Титан привычек",
        "Грандмастер",
        "Абсолют",
    ]
    level = 1
    for i, threshold in enumerate(thresholds, start=1):
        if points >= threshold:
            level = i
    if level >= len(thresholds):
        next_threshold = thresholds[-1] + (level - len(thresholds) + 1) * 600
    else:
        next_threshold = thresholds[level]
    current_threshold = thresholds[min(level - 1, len(thresholds) - 1)]
    title = titles[min(level - 1, len(titles) - 1)]
    return level, current_threshold, next_threshold, title


def weekly_theme(day: date | None = None) -> tuple[str, str]:
    day = day or utc_now().date()
    idx = day.isocalendar().week % len(WEEKLY_THEMES)
    return WEEKLY_THEMES[idx]


def random_bool(chance: float) -> bool:
    return random.random() < chance
