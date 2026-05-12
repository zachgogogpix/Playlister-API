import asyncpg
import os
from typing import Optional, List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

_pool: Optional[asyncpg.Pool] = None


def _dsn() -> str:
    ssl = "require" if os.getenv("DB_SSL_REQUIRED", "true").lower() == "true" else "disable"
    return (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PWD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT', 25060)}"
        f"/{os.getenv('DB', 'defaultdb')}?sslmode={ssl}"
    )


async def init_pool():
    global _pool
    _pool = await asyncpg.create_pool(_dsn(), min_size=2, max_size=20, command_timeout=60)


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()


def get_pool() -> asyncpg.Pool:
    return _pool


async def create_tables():
    async with _pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist (
                id SERIAL PRIMARY KEY,
                title TEXT NOT NULL,
                image_url TEXT,
                image_key TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS playlist_video (
                id SERIAL PRIMARY KEY,
                playlist_id INTEGER REFERENCES playlist(id) ON DELETE CASCADE,
                video_id INTEGER REFERENCES video(id) ON DELETE CASCADE,
                "order" INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(playlist_id, video_id)
            )
        """)
