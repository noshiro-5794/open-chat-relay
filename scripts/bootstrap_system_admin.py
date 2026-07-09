#!/usr/bin/env python3
# ruff: noqa: E402
import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from app.core.config import Settings
from app.core.security import hash_password
from app.models import User
from app.services.auth import normalize_email
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create or reset a local OpenChatRelay system administrator.",
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--display-name", default="System Administrator")
    parser.add_argument("--database-url", default=None)
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    settings = Settings()
    database_url = args.database_url or settings.database_url
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        email = normalize_email(args.email)
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(
                email=email,
                display_name=args.display_name.strip(),
                password_hash=hash_password(args.password),
                is_active=True,
                is_system_admin=True,
            )
            session.add(user)
            action = "created"
        else:
            user.display_name = args.display_name.strip() or user.display_name
            user.password_hash = hash_password(args.password)
            user.is_active = True
            user.is_system_admin = True
            action = "updated"

        await session.commit()
        await session.refresh(user)
        print(f"System admin {action}: {user.email}")

    await engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
