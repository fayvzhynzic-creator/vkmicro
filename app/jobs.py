from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.bot_logic import assign_today_task, due_for_daily, due_for_reminder, send_evening_reminder
from app.database import session_scope
from app.models import Assignment, User
from app.utils import local_today, utc_now

logger = logging.getLogger(__name__)


def run_due_notifications(now: datetime | None = None) -> dict[str, int]:
    """Send daily tasks and evening reminders for users whose local time is due.

    The assignment table has a unique (user_id, due_date) constraint, so this job is
    safe to run from both the web process and an external cron process.
    """
    now = now or utc_now()
    daily_sent = 0
    reminders_sent = 0

    with session_scope() as session:
        users = session.scalars(
            select(User).where(User.state == "active", User.is_active.is_(True), User.is_blocked.is_(False))
        ).all()
        for user in users:
            try:
                today = local_today(user.timezone)
                existing_today = session.scalar(
                    select(Assignment).where(Assignment.user_id == user.id, Assignment.due_date == today)
                )
                if not existing_today and due_for_daily(user, now):
                    assignment = assign_today_task(session, user, reason="daily")
                    if assignment:
                        daily_sent += 1
                elif existing_today and due_for_reminder(user, existing_today, now):
                    send_evening_reminder(user, existing_today)
                    reminders_sent += 1
                session.flush()
            except Exception:
                logger.exception("Failed to process due notification for user_id=%s", user.id)

    return {"daily_sent": daily_sent, "reminders_sent": reminders_sent}
