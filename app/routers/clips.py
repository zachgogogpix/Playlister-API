from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
import json
import os

from ..database import get_pool
from ..services.mux import enable_mp4_support, wait_for_mp4_ready, build_mp4_url, extract_playback_id
from ..services.clipper import trim_clip

router = APIRouter()

CLIPS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "clips")


async def _clip_event_stream(video_id: int):
    pool = get_pool()

    def event(name: str, data: dict) -> str:
        return f"event: {name}\ndata: {json.dumps(data)}\n\n"

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """SELECT v.clip_start_ms, v.clip_end_ms, v.video_url,
                          m.asset_id, m.playback_id
                   FROM video v
                   LEFT JOIN mux m ON m.video_id = v.id
                   WHERE v.id = $1""",
                video_id
            )

        if not row:
            yield event("error", {"message": "Video not found"})
            return

        d = dict(row)
        clip_start = d.get("clip_start_ms") or 0
        clip_end = d.get("clip_end_ms") or 30000
        asset_id = d.get("asset_id")
        playback_id = d.get("playback_id") or extract_playback_id(d.get("video_url", ""))

        if not playback_id:
            yield event("error", {"message": "Cannot determine Mux playback ID"})
            return

        yield event("status", {"step": 1, "message": "Enabling Mux MP4 support..."})

        if asset_id:
            status = await enable_mp4_support(asset_id)

            if status == "already_ready":
                # Asset is already prepared, skip waiting
                yield event("status", {"step": 3, "message": "Asset ready. Generating clip..."})
            else:
                # Need to wait for MP4 rendering (status: "enabled" or "already_enabled")
                yield event("status", {"step": 2, "message": "Waiting for MP4 render (may take 1-2 minutes)..."})
                await wait_for_mp4_ready(asset_id)
                yield event("status", {"step": 3, "message": "MP4 ready. Generating clip..."})
        else:
            yield event("status", {"step": 3, "message": "Generating clip..."})

        mp4_url = build_mp4_url(playback_id)
        clip_bytes = await trim_clip(mp4_url, clip_start, clip_end)

        os.makedirs(CLIPS_DIR, exist_ok=True)
        filename = f"clip_{video_id}.mp4"
        filepath = os.path.join(CLIPS_DIR, filename)
        with open(filepath, "wb") as f:
            f.write(clip_bytes)

        yield event("done", {"download_url": f"/clips/{filename}", "filename": filename})

    except Exception as e:
        yield event("error", {"message": str(e)})


@router.get("/{video_id}/generate")
async def generate_clip(video_id: int):
    return StreamingResponse(
        _clip_event_stream(video_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{video_id}/times")
async def get_clip_times(video_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, clip_start_ms, clip_end_ms FROM video WHERE id = $1", video_id
        )
    if not row:
        raise HTTPException(status_code=404, detail="Video not found")
    return dict(row)
