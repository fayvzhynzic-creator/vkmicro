from __future__ import annotations

import json
import logging
import random
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import and_, desc, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.content import CATEGORY_NAMES, DIFFICULTY_NAMES, RANDOM_NAMES, REFLECTIONS
from app.keyboards import (
    empty_keyboard,
    main_keyboard,
    onboarding_keyboard,
    settings_keyboard,
    stats_inline_keyboard,
    task_keyboard,
)
from app.models import Achievement, Assignment, Task, User, UserAchievement
from app.utils import (
    dump_categories,
    level_for_points,
    load_categories,
    local_now,
    local_today,
    normalize_hhmm,
    parse_hhmm,
    random_bool,
    safe_zone,
    sanitize_name,
    utc_now,
    week_key_for,
    weekly_theme,
)
from app.vk_client import VKApiError, SentMessage, vk

logger = logging.getLogger(__name__)

BLOCKING_ERROR_CODES = {901, 902, 917}
ALL_CATEGORIES = list(CATEGORY_NAMES.keys())
DIFFICULTY_BY_MODE = {
    "easy": [1],
    "normal": [1, 2],
    "hard": [2, 3],
    "mixed": [1, 2, 3],
}


def safe_send(user: User, message: str, keyboard: str | None = None) -> SentMessage | None:
    try:
        return vk.send_message(user.peer_id, message, keyboard=keyboard)
    except VKApiError as exc:
        if exc.code in BLOCKING_ERROR_CODES:
            user.is_blocked = True
            logger.warning("User %s blocked bot or cannot receive messages: %s", user.vk_user_id, exc)
        else:
            logger.exception("VK API send failed for user %s", user.vk_user_id)
        return None
    except Exception:
        logger.exception("Could not send VK message to user %s", user.vk_user_id)
        return None


def get_or_create_user(session: Session, vk_user_id: int, peer_id: int) -> tuple[User, bool]:
    user = session.scalar(select(User).where(User.vk_user_id == vk_user_id))
    created = False
    if not user:
        user = User(
            vk_user_id=vk_user_id,
            peer_id=peer_id,
            timezone=settings.default_timezone,
            daily_time=settings.default_daily_time,
            reminder_time=settings.default_reminder_time,
            categories_json=dump_categories(["health", "mind", "order", "social", "creativity"]),
            state="awaiting_name",
        )
        session.add(user)
        session.flush()
        created = True
    else:
        user.peer_id = peer_id
        user.is_blocked = False
    return user, created


def welcome_text() -> str:
    return (
        f"Привет! Я {settings.bot_name} — бот маленьких дел.\n\n"
        "Правило простое: 1 день = 1 маленькое дело. "
        "Каждый день я присылаю задание, ты жмёшь «✅ Сделано!», а серия растёт.\n\n"
        "Если пропустишь день — серия сгорит, но раз в неделю есть 1 жизнь 🛟.\n\n"
        "Как тебя называть? Напиши имя или нажми «🎲 Случайное имя»."
    )


def help_text() -> str:
    return (
        f"{settings.bot_name}: как это работает\n\n"
        "• Каждый день приходит маленькое задание.\n"
        "• Нажимаешь «✅ Сделано!» — получаешь очки, монеты, серию и шанс на ачивку.\n"
        "• Если день пропущен, бот тратит 1 жизнь в неделю. Если жизни нет — серия обнуляется.\n"
        "• В настройках можно менять время, часовой пояс, категории и сложность.\n\n"
        "Команды: «статистика», «лидерборд», «настройки», «задание», «неделя», «помощь»."
    )


def finish_registration(session: Session, user: User, raw_name: str) -> None:
    user.nickname = sanitize_name(raw_name)
    user.state = "active"
    session.flush()
    safe_send(
        user,
        f"Отлично, {user.nickname}! Дальше всё просто: я буду присылать по одному маленькому делу в день.\n\n"
        f"По умолчанию: {user.daily_time}, часовой пояс {user.timezone}. Это можно поменять в настройках.",
        keyboard=main_keyboard(),
    )
    send_profile(session, user, intro="Вот твой стартовый профиль 👇")
    assign_today_task(session, user, reason="registration")


def handle_message_new(session: Session, message: dict[str, Any]) -> None:
    vk_user_id = int(message.get("from_id") or 0)
    peer_id = int(message.get("peer_id") or vk_user_id)
    text = (message.get("text") or "").strip()
    if vk_user_id <= 0:
        return

    user, created = get_or_create_user(session, vk_user_id, peer_id)

    lower = text.lower()
    if created:
        safe_send(user, welcome_text(), keyboard=onboarding_keyboard())
        return

    if user.state == "awaiting_name":
        if "случай" in lower or "🎲" in text:
            finish_registration(session, user, random.choice(RANDOM_NAMES))
            return
        if lower in {"начать", "/start", "start", "привет", "меню"}:
            safe_send(user, welcome_text(), keyboard=onboarding_keyboard())
            return
        if text:
            finish_registration(session, user, text)
            return
        safe_send(user, welcome_text(), keyboard=onboarding_keyboard())
        return

    if lower in {"начать", "/start", "start", "привет", "меню"}:
        safe_send(user, f"На связи, {user.nickname or 'герой'} 👋", keyboard=main_keyboard())
        return

    if "стат" in lower or "📊" in text:
        send_profile(session, user)
        return

    if "лидер" in lower or "топ" in lower or "🏆" in text:
        send_leaderboard(session, user)
        return

    if "настрой" in lower or "⚙" in text:
        send_settings(user)
        return

    if "помощ" in lower or "❓" in text:
        safe_send(user, help_text(), keyboard=main_keyboard())
        return

    if "недел" in lower or "🔥" in text:
        send_weekly_theme(user)
        return

    if "задани" in lower or "дело" in lower or "🎲" in text:
        assign_today_task(session, user, reason="manual")
        return

    if lower in {"сделано", "готово", "выполнено", "+"} or "✅" in text:
        assignment = get_today_pending_assignment(session, user)
        if assignment:
            complete_assignment(session, user, assignment)
        else:
            safe_send(user, "На сегодня нет активного задания. Нажми «🎲 Задание сейчас».", keyboard=main_keyboard())
        return

    new_time = normalize_hhmm(text)
    if new_time:
        user.daily_time = new_time
        safe_send(user, f"Готово. Теперь ежедневное задание будет приходить примерно в {new_time} по часовому поясу {user.timezone}.")
        return

    safe_send(
        user,
        "Не совсем понял. Можно нажать кнопку в меню или написать: статистика, задание, настройки, лидерборд.",
        keyboard=main_keyboard(),
    )


def parse_payload(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"cmd": raw}
    return {}


def handle_message_event(session: Session, obj: dict[str, Any]) -> None:
    user_id = int(obj.get("user_id") or 0)
    peer_id = int(obj.get("peer_id") or user_id)
    event_id = obj.get("event_id")
    if user_id <= 0:
        return
    user, _ = get_or_create_user(session, user_id, peer_id)
    payload = parse_payload(obj.get("payload"))
    cmd = str(payload.get("cmd", "")).lower()

    def snackbar(text: str) -> None:
        if event_id:
            vk.answer_event(str(event_id), user_id=user_id, peer_id=peer_id, text=text)

    if user.state == "awaiting_name":
        snackbar("Сначала выбери имя")
        safe_send(user, welcome_text(), keyboard=onboarding_keyboard())
        return

    if cmd == "done":
        assignment = get_assignment_for_user(session, user, payload.get("assignment_id"))
        if assignment:
            complete_assignment(session, user, assignment)
            snackbar("Засчитано! Серия обновлена ✅")
        else:
            snackbar("Задание не найдено")
        return

    if cmd == "swap":
        assignment = get_assignment_for_user(session, user, payload.get("assignment_id"))
        if assignment:
            swapped = swap_assignment(session, user, assignment)
            snackbar("Новое задание готово" if swapped else "Сменить не получилось")
        else:
            snackbar("Задание не найдено")
        return

    if cmd == "stats":
        send_profile(session, user)
        snackbar("Статистика отправлена")
        return

    if cmd == "leaderboard":
        send_leaderboard(session, user)
        snackbar("Топ отправлен")
        return

    if cmd == "share":
        send_share_text(user)
        snackbar("Текст отправлен")
        return

    if cmd == "toggle_category":
        category = str(payload.get("category", ""))
        if category in CATEGORY_NAMES:
            categories = load_categories(user.categories_json)
            if category in categories and len(categories) > 1:
                categories.remove(category)
                snackbar("Категория выключена")
            elif category not in categories:
                categories.append(category)
                snackbar("Категория включена")
            else:
                snackbar("Нужна хотя бы одна категория")
            user.categories_json = dump_categories(categories)
            session.flush()
            send_settings(user)
        return

    if cmd == "difficulty":
        mode = str(payload.get("mode", "mixed"))
        if mode in DIFFICULTY_BY_MODE:
            user.difficulty_mode = mode
            session.flush()
            send_settings(user)
            snackbar("Сложность обновлена")
        return

    if cmd == "time":
        value = str(payload.get("value", settings.default_daily_time))
        if normalize_hhmm(value):
            user.daily_time = value
            session.flush()
            send_settings(user)
            snackbar(f"Время: {value}")
        return

    if cmd == "timezone":
        value = str(payload.get("value", settings.default_timezone))
        # safe_zone validates and falls back if invalid.
        user.timezone = safe_zone(value).key
        session.flush()
        send_settings(user)
        snackbar(f"Часовой пояс: {user.timezone}")
        return

    snackbar("Готово")


def get_assignment_for_user(session: Session, user: User, assignment_id: Any) -> Assignment | None:
    try:
        aid = int(assignment_id)
    except (TypeError, ValueError):
        return None
    return session.scalar(select(Assignment).where(Assignment.id == aid, Assignment.user_id == user.id))


def get_today_pending_assignment(session: Session, user: User) -> Assignment | None:
    today = local_today(user.timezone)
    return session.scalar(
        select(Assignment).where(
            Assignment.user_id == user.id,
            Assignment.due_date == today,
            Assignment.status == "pending",
        )
    )


def ensure_weekly_lives(user: User, today: date) -> None:
    current_week = week_key_for(today)
    if user.lives_week_key != current_week:
        user.lives_week_key = current_week
        user.weekly_lives_left = 1


def close_missed_days(session: Session, user: User, today: date, notify: bool = False) -> list[str]:
    ensure_weekly_lives(user, today)
    pending_old = session.scalars(
        select(Assignment)
        .where(
            Assignment.user_id == user.id,
            Assignment.status == "pending",
            Assignment.due_date < today,
        )
        .order_by(Assignment.due_date.asc())
    ).all()
    notices: list[str] = []
    for assignment in pending_old:
        assignment.status = "missed"
        if user.weekly_lives_left > 0:
            user.weekly_lives_left -= 1
            if user.last_done_date is None or assignment.due_date > user.last_done_date:
                user.last_done_date = assignment.due_date
            notices.append(
                f"🛟 Пропуск за {assignment.due_date.isoformat()} закрыт жизнью. Серия сохранена, жизней на неделе: {user.weekly_lives_left}."
            )
        else:
            if user.current_streak > 0:
                notices.append(f"💔 Пропуск за {assignment.due_date.isoformat()}: серия обнулилась.")
            user.current_streak = 0
    if notify:
        for text in notices[:3]:
            safe_send(user, text)
        if len(notices) > 3:
            safe_send(user, f"И ещё {len(notices) - 3} старых пропуска обработаны.")
    return notices


def assign_today_task(session: Session, user: User, reason: str = "daily") -> Assignment | None:
    if not user.is_active or user.is_blocked:
        return None

    today = local_today(user.timezone)
    close_missed_days(session, user, today, notify=(reason != "daily"))

    existing = session.scalar(select(Assignment).where(Assignment.user_id == user.id, Assignment.due_date == today))
    if existing:
        if existing.status == "pending":
            if reason == "manual":
                safe_send(
                    user,
                    "Сегодняшнее задание уже выдано 👇\n\n" + format_task_body(existing, user, surprise=False),
                    keyboard=task_keyboard(existing.id),
                )
            return existing
        if existing.status == "done":
            if reason == "manual":
                safe_send(user, "Сегодняшнее дело уже закрыто ✅ Завтра будет новое.", keyboard=main_keyboard())
            return existing

    task = choose_task(session, user)
    if not task:
        safe_send(user, "Не нашёл активных заданий под твои настройки. Включи больше категорий в настройках.")
        return None

    assignment = Assignment(user_id=user.id, task_id=task.id, due_date=today, peer_id=user.peer_id, status="pending")
    session.add(assignment)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        # Race protection for web scheduler + cron. Re-read existing assignment.
        return session.scalar(select(Assignment).where(Assignment.user_id == user.id, Assignment.due_date == today))

    surprise = random_bool(0.12)
    sent = safe_send(user, format_task_body(assignment, user, surprise=surprise), keyboard=task_keyboard(assignment.id))
    if sent:
        assignment.message_id = sent.message_id
        assignment.conversation_message_id = sent.conversation_message_id
    return assignment


def choose_task(session: Session, user: User, exclude_task_id: int | None = None) -> Task | None:
    categories = load_categories(user.categories_json)
    difficulties = DIFFICULTY_BY_MODE.get(user.difficulty_mode, [1, 2, 3])

    recent_task_ids = {
        row[0]
        for row in session.execute(
            select(Assignment.task_id)
            .where(Assignment.user_id == user.id)
            .order_by(Assignment.sent_at.desc())
            .limit(14)
        ).all()
    }
    if exclude_task_id:
        recent_task_ids.add(exclude_task_id)

    base_query = select(Task).where(
        Task.is_active.is_(True),
        Task.category.in_(categories),
        Task.difficulty.in_(difficulties),
    )
    candidates = session.scalars(base_query.where(~Task.id.in_(recent_task_ids))).all()
    if not candidates:
        candidates = session.scalars(base_query).all()
    return random.choice(candidates) if candidates else None


def format_task_body(assignment: Assignment, user: User, surprise: bool = False) -> str:
    task = assignment.task
    category = CATEGORY_NAMES.get(task.category, task.category)
    difficulty = DIFFICULTY_NAMES.get(task.difficulty, "обычное")
    theme_category, theme_text = weekly_theme(assignment.due_date)
    theme_line = f"\n🔥 {theme_text}" if theme_category == task.category else ""
    surprise_line = "\n🎲 Сюрприз‑день: за это дело настроение получает +1." if surprise else ""
    return (
        f"Дело дня на {assignment.due_date.isoformat()}\n\n"
        f"{task.text}\n\n"
        f"Категория: {category}\n"
        f"Сложность: {difficulty}\n"
        f"Награда: +{task.points} очков, +{max(1, task.points // 10)} монет"
        f"{theme_line}{surprise_line}\n\n"
        "1 день = 1 маленькое дело. Когда сделаешь — жми кнопку ниже 👇"
    )


def swap_assignment(session: Session, user: User, assignment: Assignment) -> bool:
    today = local_today(user.timezone)
    if assignment.status != "pending" or assignment.due_date != today:
        safe_send(user, "Сменить можно только сегодняшнее активное задание.")
        return False

    if assignment.swap_count >= 2:
        if user.coins < 5:
            safe_send(user, "Бесплатные замены на сегодня закончились. Нужно 5 монет, а их пока не хватает.")
            return False
        user.coins -= 5

    new_task = choose_task(session, user, exclude_task_id=assignment.task_id)
    if not new_task:
        safe_send(user, "Не нашёл другое задание под твои настройки.")
        return False

    assignment.task_id = new_task.id
    assignment.swap_count += 1
    session.flush()
    text = "🔁 Заменил задание. Новое дело дня:\n\n" + format_task_body(assignment, user, surprise=False)
    try_edit_assignment_message(assignment, text, keyboard=task_keyboard(assignment.id), fallback_user=user)
    return True


def complete_assignment(session: Session, user: User, assignment: Assignment) -> None:
    today = local_today(user.timezone)
    close_missed_days(session, user, today, notify=False)
    session.refresh(assignment)

    if assignment.status == "done":
        safe_send(user, "Это задание уже было засчитано ✅", keyboard=main_keyboard())
        return

    if assignment.status != "pending":
        safe_send(user, "Это задание уже не активно. Возьми сегодняшнее через «🎲 Задание сейчас».", keyboard=main_keyboard())
        return

    if assignment.due_date != today:
        assignment.status = "missed"
        safe_send(user, "Старое задание уже просрочено. Сегодня можно взять новое.", keyboard=main_keyboard())
        return

    assignment.status = "done"
    assignment.done_at = utc_now()

    yesterday = today - timedelta(days=1)
    if user.last_done_date == today:
        pass
    elif user.last_done_date == yesterday and user.current_streak > 0:
        user.current_streak += 1
    else:
        user.current_streak = 1
    user.last_done_date = today
    user.best_streak = max(user.best_streak, user.current_streak)
    user.total_done += 1
    user.points += assignment.task.points
    user.coins += max(1, assignment.task.points // 10)
    ensure_weekly_lives(user, today)
    session.flush()

    level, current_threshold, next_threshold, title = level_for_points(user.points)
    done_text = (
        f"✅ Выполнено!\n\n"
        f"{assignment.task.text}\n\n"
        f"+{assignment.task.points} очков · серия: {user.current_streak} дн. · уровень {level} «{title}»\n"
        f"До следующего уровня: {max(0, next_threshold - user.points)} очков."
    )
    try_edit_assignment_message(assignment, done_text, keyboard=empty_keyboard(inline=True), fallback_user=user)

    new_achievements = award_achievements(session, user)
    session.flush()

    reflection = random.choice(REFLECTIONS)
    after_text = f"Вопрос дня: {reflection}"
    if new_achievements:
        badges = "\n".join(f"{a.emoji} {a.title} — {a.description}" for a in new_achievements)
        after_text = f"Новая ачивка!\n{badges}\n\n" + after_text
    safe_send(user, after_text, keyboard=main_keyboard())


def try_edit_assignment_message(assignment: Assignment, text: str, keyboard: str | None, fallback_user: User) -> None:
    if assignment.message_id is None and assignment.conversation_message_id is None:
        safe_send(fallback_user, text, keyboard=keyboard)
        return
    try:
        vk.edit_message(
            peer_id=assignment.peer_id,
            message=text,
            message_id=assignment.message_id,
            conversation_message_id=assignment.conversation_message_id,
            keyboard=keyboard,
        )
    except Exception:
        logger.exception("Could not edit assignment message %s; sending fallback", assignment.id)
        safe_send(fallback_user, text, keyboard=keyboard)


def award_achievements(session: Session, user: User) -> list[Achievement]:
    existing = {
        row[0]
        for row in session.execute(select(UserAchievement.achievement_code).where(UserAchievement.user_id == user.id)).all()
    }

    category_counts = {
        row[0]: int(row[1])
        for row in session.execute(
            select(Task.category, func.count(Assignment.id))
            .join(Assignment, Assignment.task_id == Task.id)
            .where(Assignment.user_id == user.id, Assignment.status == "done")
            .group_by(Task.category)
        ).all()
    }
    level, _, _, _ = level_for_points(user.points)

    checks = {
        "first_done": user.total_done >= 1,
        "streak_3": user.current_streak >= 3,
        "streak_7": user.current_streak >= 7,
        "streak_14": user.current_streak >= 14,
        "streak_30": user.current_streak >= 30,
        "done_10": user.total_done >= 10,
        "done_50": user.total_done >= 50,
        "done_100": user.total_done >= 100,
        "health_5": category_counts.get("health", 0) >= 5,
        "order_5": category_counts.get("order", 0) >= 5,
        "social_5": category_counts.get("social", 0) >= 5,
        "mind_5": category_counts.get("mind", 0) >= 5,
        "creative_5": category_counts.get("creativity", 0) >= 5,
        "level_5": level >= 5,
    }

    to_award_codes = [code for code, ok in checks.items() if ok and code not in existing]
    if not to_award_codes:
        return []

    achievements = session.scalars(select(Achievement).where(Achievement.code.in_(to_award_codes))).all()
    by_code = {a.code: a for a in achievements}
    awarded: list[Achievement] = []
    for code in to_award_codes:
        achievement = by_code.get(code)
        if achievement:
            session.add(UserAchievement(user_id=user.id, achievement_code=code))
            awarded.append(achievement)
    return awarded


def send_profile(session: Session, user: User, intro: str | None = None) -> None:
    today = local_today(user.timezone)
    ensure_weekly_lives(user, today)
    level, current_threshold, next_threshold, title = level_for_points(user.points)
    categories = load_categories(user.categories_json)
    category_text = ", ".join(CATEGORY_NAMES.get(c, c) for c in categories)
    achievement_count = session.scalar(select(func.count(UserAchievement.id)).where(UserAchievement.user_id == user.id)) or 0
    pending = get_today_pending_assignment(session, user)
    pending_line = "\nСегодня: есть активное задание 👇" if pending else "\nСегодня: активного задания нет."
    progress = f"{user.points - current_threshold}/{next_threshold - current_threshold}" if next_threshold > current_threshold else "max"

    text = (
        (intro + "\n\n" if intro else "")
        + f"📊 Профиль: {user.nickname or 'Герой'}\n\n"
        f"🔥 Текущая серия: {user.current_streak} дн.\n"
        f"🏆 Лучшая серия: {user.best_streak} дн.\n"
        f"✅ Выполнено всего: {user.total_done}\n"
        f"⭐ Очки: {user.points}\n"
        f"💰 Монеты: {user.coins}\n"
        f"⬆️ Уровень {level}: {title} ({progress})\n"
        f"🛟 Жизни на этой неделе: {user.weekly_lives_left}\n"
        f"🎖 Ачивки: {achievement_count}\n"
        f"⏰ Рассылка: {user.daily_time} · {user.timezone}\n"
        f"🎛 Категории: {category_text}"
        f"{pending_line}"
    )
    safe_send(user, text, keyboard=stats_inline_keyboard())


def send_leaderboard(session: Session, user: User) -> None:
    top_users = session.scalars(
        select(User)
        .where(User.state == "active", User.is_active.is_(True))
        .order_by(desc(User.current_streak), desc(User.total_done), desc(User.points))
        .limit(10)
    ).all()
    if not top_users:
        safe_send(user, "Лидерборд пока пуст.", keyboard=main_keyboard())
        return
    lines = ["🏆 Лидерборд по серии", ""]
    medals = ["🥇", "🥈", "🥉"]
    for idx, u in enumerate(top_users, start=1):
        mark = medals[idx - 1] if idx <= 3 else f"{idx}."
        you = " ← ты" if u.id == user.id else ""
        lines.append(f"{mark} {u.nickname or 'Герой'} — {u.current_streak} дн., всего {u.total_done}{you}")
    lines.append("\nРейтинг не показывает VK ID — только выбранные имена.")
    safe_send(user, "\n".join(lines), keyboard=main_keyboard())


def send_settings(user: User) -> None:
    categories = load_categories(user.categories_json)
    text = (
        "⚙️ Настройки\n\n"
        f"⏰ Время: {user.daily_time}\n"
        f"🌍 Часовой пояс: {user.timezone}\n"
        f"🎚 Сложность: {user.difficulty_mode}\n"
        "🎛 Категории можно включать/выключать кнопками ниже.\n\n"
        "Можно также просто написать время сообщением, например: 08:30."
    )
    safe_send(user, text, keyboard=settings_keyboard(categories, user.difficulty_mode))


def send_weekly_theme(user: User) -> None:
    category, text = weekly_theme(local_today(user.timezone))
    safe_send(
        user,
        f"🔥 Тема недели\n\n{text}\n\nКатегория недели: {CATEGORY_NAMES.get(category, category)}. "
        "Задания из этой категории иногда будут подсвечиваться как недельный челлендж.",
        keyboard=main_keyboard(),
    )


def send_share_text(user: User) -> None:
    text = (
        "📣 Текст, который можно кинуть в сторис/чат:\n\n"
        f"Я уже закрыл(а) {user.total_done} маленьких дел и держу серию {user.current_streak} дней в боте «{settings.bot_name}». "
        "1 день = 1 маленькое дело. Кто со мной? ✅"
    )
    safe_send(user, text, keyboard=main_keyboard())


def due_for_daily(user: User, now_utc: datetime | None = None) -> bool:
    if not user.is_active or user.is_blocked or user.state != "active":
        return False
    now = now_utc or utc_now()
    local = now.astimezone(safe_zone(user.timezone))
    due_time = parse_hhmm(user.daily_time, settings.default_daily_time)
    return local.time() >= due_time


def due_for_reminder(user: User, assignment: Assignment, now_utc: datetime | None = None) -> bool:
    if assignment.status != "pending" or assignment.reminded_at is not None:
        return False
    now = now_utc or utc_now()
    local = now.astimezone(safe_zone(user.timezone))
    reminder_time = parse_hhmm(user.reminder_time, settings.default_reminder_time)
    return local.date() == assignment.due_date and local.time() >= reminder_time


def send_evening_reminder(user: User, assignment: Assignment) -> None:
    assignment.reminded_at = utc_now()
    safe_send(
        user,
        "Мягкое напоминание 👀\n\n"
        "Сегодняшнее маленькое дело ещё не закрыто. Можно сделать в супер‑лайт режиме — главное поставить галочку.\n\n"
        + format_task_body(assignment, user, surprise=False),
        keyboard=task_keyboard(assignment.id),
    )
