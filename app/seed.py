from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content import ACHIEVEMENTS, TASKS
from app.models import Achievement, Task


def seed_content(session: Session) -> None:
    existing_tasks = {row[0] for row in session.execute(select(Task.text)).all()}
    for text, category, difficulty, points in TASKS:
        if text not in existing_tasks:
            session.add(Task(text=text, category=category, difficulty=difficulty, points=points, is_active=True))

    existing_achievements = {row[0] for row in session.execute(select(Achievement.code)).all()}
    for code, title, description, emoji in ACHIEVEMENTS:
        if code not in existing_achievements:
            session.add(Achievement(code=code, title=title, description=description, emoji=emoji))
