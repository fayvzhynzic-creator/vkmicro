from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vk_user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True, nullable=False)
    peer_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    nickname: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    state: Mapped[str] = mapped_column(String(40), default="awaiting_name", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    daily_time: Mapped[str] = mapped_column(String(5), default="09:00", nullable=False)
    reminder_time: Mapped[str] = mapped_column(String(5), default="20:00", nullable=False)
    categories_json: Mapped[str] = mapped_column(Text, default='["health","mind","order","social","creativity"]', nullable=False)
    difficulty_mode: Mapped[str] = mapped_column(String(16), default="mixed", nullable=False)  # easy / normal / hard / mixed

    current_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    best_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_done: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    weekly_lives_left: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    lives_week_key: Mapped[Optional[str]] = mapped_column(String(12), nullable=True)
    last_done_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    achievements: Mapped[list["UserAchievement"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    difficulty: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1 easy, 2 normal, 3 hard
    points: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    assignments: Mapped[list["Assignment"]] = relationship(back_populates="task")


class Assignment(Base):
    __tablename__ = "assignments"
    __table_args__ = (UniqueConstraint("user_id", "due_date", name="uq_assignment_user_due_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"), nullable=False)
    due_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True, nullable=False)  # pending/done/missed/swapped
    peer_id: Mapped[int] = mapped_column(Integer, nullable=False)
    message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    conversation_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    swap_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reminded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship(back_populates="assignments")
    task: Mapped[Task] = relationship(back_populates="assignments")


class Achievement(Base):
    __tablename__ = "achievements"

    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    emoji: Mapped[str] = mapped_column(String(8), default="🏅", nullable=False)

    users: Mapped[list["UserAchievement"]] = relationship(back_populates="achievement")


class UserAchievement(Base):
    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_code", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    achievement_code: Mapped[str] = mapped_column(ForeignKey("achievements.code"), nullable=False)
    awarded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship(back_populates="achievements")
    achievement: Mapped[Achievement] = relationship(back_populates="users")
