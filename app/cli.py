from __future__ import annotations

import argparse
import json

from app.database import init_db, session_scope
from app.jobs import run_due_notifications
from app.seed import seed_content


def main() -> None:
    parser = argparse.ArgumentParser(description="VK Micro Habits Bot maintenance CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db", help="Create database tables and seed tasks")
    sub.add_parser("run-due", help="Send due daily tasks/reminders and exit")
    args = parser.parse_args()

    if args.command == "init-db":
        init_db()
        with session_scope() as session:
            seed_content(session)
        print("Database initialized")
    elif args.command == "run-due":
        init_db()
        with session_scope() as session:
            seed_content(session)
        print(json.dumps(run_due_notifications(), ensure_ascii=False))


if __name__ == "__main__":
    main()
