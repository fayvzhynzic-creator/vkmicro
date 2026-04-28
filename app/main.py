from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, select

from app.bot_logic import handle_message_event, handle_message_new
from app.config import settings
from app.database import init_db, session_scope
from app.jobs import run_due_notifications
from app.models import Assignment, User
from app.scheduler import start_scheduler, stop_scheduler
from app.seed import seed_content

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with session_scope() as session:
        seed_content(session)
    start_scheduler()
    try:
        yield
    finally:
        stop_scheduler()


app = FastAPI(title="VK Micro Habits Bot", version="1.0.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def index() -> dict[str, Any]:
    callback_url = (settings.public_base_url.rstrip("/") + "/vk/callback") if settings.public_base_url else "/vk/callback"
    return {
        "name": settings.bot_name,
        "status": "running",
        "vk_callback_url": callback_url,
        "docs": "Use POST /vk/callback as VK Callback API endpoint.",
    }


@app.post("/vk/callback", response_class=PlainTextResponse)
async def vk_callback(request: Request) -> PlainTextResponse:
    data = await request.json()
    event_type = data.get("type")

    if settings.vk_group_id is not None and data.get("group_id") not in {settings.vk_group_id, str(settings.vk_group_id)}:
        logger.warning("Unexpected VK group_id: %s", data.get("group_id"))
        raise HTTPException(status_code=403, detail="Unexpected group_id")

    if settings.vk_secret and data.get("secret") != settings.vk_secret:
        logger.warning("Invalid VK secret")
        raise HTTPException(status_code=403, detail="Invalid secret")

    if event_type == "confirmation":
        return PlainTextResponse(settings.vk_confirmation_token or "")

    with session_scope() as session:
        if event_type == "message_new":
            message = (data.get("object") or {}).get("message") or data.get("object") or {}
            handle_message_new(session, message)
        elif event_type == "message_event":
            obj = data.get("object") or {}
            handle_message_event(session, obj)
        else:
            # VK expects ok for events you don't use too.
            logger.debug("Ignored VK event type: %s", event_type)

    return PlainTextResponse("ok")


@app.post("/internal/run-due")
def run_due(x_cron_secret: str | None = Header(default=None, alias="X-Cron-Secret")) -> JSONResponse:
    if settings.cron_secret and x_cron_secret != settings.cron_secret:
        raise HTTPException(status_code=403, detail="Invalid cron secret")
    result = run_due_notifications()
    return JSONResponse(result)


@app.get("/admin/stats")
def admin_stats(token: str | None = None) -> dict[str, Any]:
    if settings.admin_token and token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Invalid admin token")
    with session_scope() as session:
        users_total = session.scalar(select(func.count(User.id))) or 0
        users_active = session.scalar(select(func.count(User.id)).where(User.state == "active", User.is_active.is_(True))) or 0
        assignments_total = session.scalar(select(func.count(Assignment.id))) or 0
        assignments_done = session.scalar(select(func.count(Assignment.id)).where(Assignment.status == "done")) or 0
    return {
        "users_total": users_total,
        "users_active": users_active,
        "assignments_total": assignments_total,
        "assignments_done": assignments_done,
    }
