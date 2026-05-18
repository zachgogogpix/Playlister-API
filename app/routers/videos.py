from fastapi import APIRouter, Query, HTTPException
from typing import Optional
import math

from ..database import get_pool
from ..models import Video, VideoListResponse, ClipUpdate, FlagsUpdate

router = APIRouter()

VIDEO_FIELDS = """
    id, title, artist, record_label, originalreleasedate, partner_account,
    video_url, thumbnail_url, album_artwork, is_active, ready_for_mux_delete,
    clip_start_ms, clip_end_ms, duration, genre, video_id::text, link_out
"""


def _row_to_video(row) -> dict:
    d = dict(row)
    if "originalreleasedate" in d and d["originalreleasedate"]:
        pass  # already a date object
    return d


@router.get("", response_model=VideoListResponse)
async def list_videos(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    artist: Optional[str] = None,
    title: Optional[str] = None,
    record_label: Optional[str] = None,
    video_id: Optional[str] = None,
    partner_account: Optional[str] = None,
    date_op: Optional[str] = Query(None, pattern="^(eq|gt|lt)$"),
    date_val: Optional[str] = None,
):
    pool = get_pool()
    conditions = []
    params = []
    idx = 1

    if artist:
        conditions.append(f"artist ILIKE ${idx}")
        params.append(f"%{artist}%")
        idx += 1
    if title:
        conditions.append(f"title ILIKE ${idx}")
        params.append(f"%{title}%")
        idx += 1
    if record_label:
        conditions.append(f"record_label ILIKE ${idx}")
        params.append(f"%{record_label}%")
        idx += 1
    if video_id:
        conditions.append(f"(id::text ILIKE ${idx} OR video_id::text ILIKE ${idx})")
        params.append(f"%{video_id}%")
        idx += 1
    if partner_account:
        conditions.append(f"partner_account = ${idx}")
        params.append(partner_account)
        idx += 1
    if date_op and date_val:
        op_map = {"eq": "=", "gt": ">", "lt": "<"}
        conditions.append(f"originalreleasedate {op_map[date_op]} ${idx}::date")
        params.append(date_val)
        idx += 1

    conditions.insert(0, "(originalreleasedate IS NULL OR originalreleasedate <= CURRENT_DATE)")
    conditions.insert(0, "is_active = TRUE")
    conditions.insert(0, "partner_account IN ('sony', 'IIP-DDS', 'DashGo', 'DPM Network', 'Horus', 'gogopix', 'Ryan Celsius Sounds', 'orchard')")
    where = "WHERE " + " AND ".join(conditions)
    offset = (page - 1) * limit

    async with pool.acquire() as conn:
        count_row = await conn.fetchrow(f"SELECT COUNT(*) as cnt FROM video {where}", *params)
        total = count_row["cnt"]

        rows = await conn.fetch(
            f"SELECT {VIDEO_FIELDS} FROM video {where} ORDER BY id DESC LIMIT ${idx} OFFSET ${idx+1}",
            *params, limit, offset
        )

    videos = [Video(**_row_to_video(r)) for r in rows]
    pages = math.ceil(total / limit) if total > 0 else 1

    return VideoListResponse(videos=videos, total=total, page=page, limit=limit, pages=pages)


@router.get("/partners")
async def get_partners():
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT DISTINCT partner_account FROM video
               WHERE partner_account IN ('sony', 'IIP-DDS', 'DashGo', 'DPM Network', 'Horus', 'gogopix', 'Ryan Celsius Sounds', 'orchard')
               AND is_active = TRUE
               ORDER BY partner_account"""
        )
    return [r["partner_account"] for r in rows]


@router.get("/{video_id}", response_model=Video)
async def get_video(video_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"SELECT {VIDEO_FIELDS} FROM video WHERE id = $1", video_id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return Video(**_row_to_video(row))


@router.patch("/{video_id}/clip", response_model=Video)
async def update_clip_times(video_id: int, body: ClipUpdate):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""UPDATE video SET clip_start_ms = $1, clip_end_ms = $2, updated_at = NOW()
                WHERE id = $3 RETURNING {VIDEO_FIELDS}""",
            body.clip_start_ms, body.clip_end_ms, video_id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return Video(**_row_to_video(row))


@router.patch("/{video_id}/flags", response_model=Video)
async def update_flags(video_id: int, body: FlagsUpdate):
    if body.is_active is None and body.ready_for_mux_delete is None:
        raise HTTPException(status_code=400, detail="No flags provided")

    pool = get_pool()
    sets = []
    params = []
    idx = 1

    if body.is_active is not None:
        sets.append(f"is_active = ${idx}")
        params.append(body.is_active)
        idx += 1
    if body.ready_for_mux_delete is not None:
        sets.append(f"ready_for_mux_delete = ${idx}")
        params.append(body.ready_for_mux_delete)
        idx += 1

    params.append(video_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE video SET {', '.join(sets)}, updated_at = NOW() WHERE id = ${idx} RETURNING {VIDEO_FIELDS}",
            *params
        )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return Video(**_row_to_video(row))
