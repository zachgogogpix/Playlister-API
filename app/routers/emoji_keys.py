import logging
import time
import uuid
from typing import Dict, List

import asyncpg
from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse

from ..database import get_pool

logger = logging.getLogger(__name__)

router = APIRouter()

KEY_GROUPS = ("genre", "mood", "tags")
MAX_KEYS_PER_GROUP = 10
DEFINITIONS_TTL_SECONDS = 300

_definitions_cache: Dict[str, object] = {"data": None, "expires_at": 0.0}


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": message})


def _empty_groups() -> Dict[str, list]:
    return {group: [] for group in KEY_GROUPS}


async def _fetch_video_keys(conn, video_id: int) -> Dict[str, List[str]]:
    rows = await conn.fetch(
        """SELECT key_group, key_value FROM video_emoji_keys
           WHERE video_id = $1
           ORDER BY key_group, key_value""",
        video_id,
    )
    result = _empty_groups()
    for r in rows:
        if r["key_group"] in result:
            result[r["key_group"]].append(r["key_value"])
    return result


@router.get("/emoji-keys/definitions")
async def get_definitions(response: Response):
    now = time.monotonic()
    if _definitions_cache["data"] is None or now >= _definitions_cache["expires_at"]:
        pool = get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """SELECT key_group, key_value, emoji, label
                   FROM key_choices_menu
                   WHERE is_active = TRUE
                   ORDER BY key_group, display_order"""
            )
        data = _empty_groups()
        for r in rows:
            if r["key_group"] in data:
                data[r["key_group"]].append(
                    {"value": r["key_value"], "emoji": r["emoji"], "label": r["label"]}
                )
        _definitions_cache["data"] = data
        _definitions_cache["expires_at"] = now + DEFINITIONS_TTL_SECONDS

    response.headers["Cache-Control"] = f"public, max-age={DEFINITIONS_TTL_SECONDS}"
    return _definitions_cache["data"]


@router.get("/videos/{video_id}/emoji-keys")
async def get_video_emoji_keys(video_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM video WHERE id = $1", video_id)
        if not exists:
            return _error(404, "Video not found")
        return await _fetch_video_keys(conn, video_id)


@router.patch("/videos/{video_id}/emoji-keys")
async def patch_video_emoji_keys(video_id: int, body: Dict[str, List[str]]):
    pool = get_pool()
    async with pool.acquire() as conn:
        # 1. Video must exist (checked first, per spec).
        exists = await conn.fetchval("SELECT 1 FROM video WHERE id = $1", video_id)
        if not exists:
            return _error(404, "Video not found")

        if not body:
            return _error(400, "No key groups provided")

        # 2a/2b. Validate group names and sizes.
        updates: Dict[str, List[str]] = {}
        for key_group, key_values in body.items():
            if key_group not in KEY_GROUPS:
                return _error(400, "Invalid key_group: must be 'genre', 'mood', or 'tags'")
            deduped = list(dict.fromkeys(key_values))
            if len(deduped) > MAX_KEYS_PER_GROUP:
                return _error(400, f"Maximum {MAX_KEYS_PER_GROUP} keys allowed per group")
            updates[key_group] = deduped

        # Validate every value against the menu for its own group, so a mood
        # value can't be saved under genre.
        for key_group, key_values in updates.items():
            if not key_values:
                continue
            valid_rows = await conn.fetch(
                """SELECT key_value FROM key_choices_menu
                   WHERE key_group = $1 AND key_value = ANY($2::text[]) AND is_active = TRUE""",
                key_group, key_values,
            )
            valid = {r["key_value"] for r in valid_rows}
            for value in key_values:
                if value not in valid:
                    return _error(
                        400, f"Invalid key_value: '{value}' not found in key_choices_menu"
                    )

        # All groups validated: apply atomically so a request never half-applies.
        try:
            async with conn.transaction():
                for key_group, key_values in updates.items():
                    await conn.execute(
                        "DELETE FROM video_emoji_keys WHERE video_id = $1 AND key_group = $2",
                        video_id, key_group,
                    )
                    if key_values:
                        # video_emoji_keys.id is a UUID with no DB default, so
                        # generate one per row here.
                        await conn.execute(
                            """INSERT INTO video_emoji_keys (id, video_id, key_group, key_value)
                               SELECT k.id, $1, $2, k.key_value
                               FROM unnest($3::uuid[], $4::text[]) AS k(id, key_value)""",
                            video_id, key_group,
                            [uuid.uuid4() for _ in key_values], key_values,
                        )
        except (asyncpg.PostgresError, asyncpg.InterfaceError) as e:
            logger.exception(
                "Failed to save emoji keys: video_id=%s body=%r error=%s sqlstate=%s",
                video_id, body, type(e).__name__, getattr(e, "sqlstate", None),
            )
            return _error(500, "Failed to save emoji keys")

        return await _fetch_video_keys(conn, video_id)
