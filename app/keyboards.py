from __future__ import annotations

import json
from typing import Any

from app.content import CATEGORY_NAMES


def _payload(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def text_button(label: str, color: str = "secondary", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "action": {
            "type": "text",
            "label": label,
            "payload": _payload(payload or {"cmd": label}),
        },
        "color": color,
    }


def callback_button(label: str, payload: dict[str, Any], color: str = "secondary") -> dict[str, Any]:
    return {
        "action": {
            "type": "callback",
            "label": label,
            "payload": _payload(payload),
        },
        "color": color,
    }


def keyboard_json(buttons: list[list[dict[str, Any]]], inline: bool = False, one_time: bool = False) -> str:
    return json.dumps({"one_time": one_time, "inline": inline, "buttons": buttons}, ensure_ascii=False)


def empty_keyboard(inline: bool = False) -> str:
    return keyboard_json([], inline=inline, one_time=False)


def main_keyboard() -> str:
    return keyboard_json(
        [
            [text_button("📊 Моя статистика", "primary"), text_button("🏆 Лидерборд", "primary")],
            [text_button("🎲 Задание сейчас", "positive"), text_button("🔥 Неделя", "secondary")],
            [text_button("⚙️ Настройки", "secondary"), text_button("❓ Помощь", "secondary")],
        ],
        inline=False,
        one_time=False,
    )


def onboarding_keyboard() -> str:
    return keyboard_json(
        [[text_button("🎲 Случайное имя", "primary")], [text_button("❓ Помощь", "secondary")]],
        inline=False,
        one_time=False,
    )


def task_keyboard(assignment_id: int) -> str:
    return keyboard_json(
        [
            [callback_button("✅ Сделано!", {"cmd": "done", "assignment_id": assignment_id}, "positive")],
            [
                callback_button("🔁 Другое", {"cmd": "swap", "assignment_id": assignment_id}, "secondary"),
                callback_button("📊 Статистика", {"cmd": "stats"}, "primary"),
            ],
        ],
        inline=True,
    )


def settings_keyboard(categories: list[str], difficulty_mode: str) -> str:
    category_rows: list[list[dict[str, Any]]] = []
    for key, label in CATEGORY_NAMES.items():
        marker = "✅" if key in categories else "➕"
        category_rows.append([callback_button(f"{marker} {label}", {"cmd": "toggle_category", "category": key}, "secondary")])

    difficulty_row = [
        callback_button(("✅ " if difficulty_mode == "easy" else "") + "Лёгкие", {"cmd": "difficulty", "mode": "easy"}, "secondary"),
        callback_button(("✅ " if difficulty_mode == "mixed" else "") + "Микс", {"cmd": "difficulty", "mode": "mixed"}, "secondary"),
    ]
    difficulty_row_2 = [
        callback_button(("✅ " if difficulty_mode == "normal" else "") + "Норм", {"cmd": "difficulty", "mode": "normal"}, "secondary"),
        callback_button(("✅ " if difficulty_mode == "hard" else "") + "Челлендж", {"cmd": "difficulty", "mode": "hard"}, "secondary"),
    ]

    rows = [
        [callback_button("⏰ 07:00", {"cmd": "time", "value": "07:00"}), callback_button("⏰ 09:00", {"cmd": "time", "value": "09:00"})],
        [callback_button("⏰ 12:00", {"cmd": "time", "value": "12:00"}), callback_button("⏰ 18:00", {"cmd": "time", "value": "18:00"})],
        [callback_button("🌍 Москва", {"cmd": "timezone", "value": "Europe/Moscow"}), callback_button("🌍 Берлин", {"cmd": "timezone", "value": "Europe/Berlin"})],
        difficulty_row,
        difficulty_row_2,
        *category_rows,
        [callback_button("📊 Моя статистика", {"cmd": "stats"}, "primary")],
    ]
    return keyboard_json(rows, inline=True)


def stats_inline_keyboard() -> str:
    return keyboard_json(
        [
            [callback_button("🏆 Лидерборд", {"cmd": "leaderboard"}, "primary")],
            [callback_button("📣 Текст для сторис", {"cmd": "share"}, "secondary")],
        ],
        inline=True,
    )
