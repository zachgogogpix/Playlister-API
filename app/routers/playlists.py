from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from typing import Optional, List

from ..database import get_pool
from ..models import (
    Playlist, PlaylistDetail, PlaylistUpdate,
    PlaylistVideoItem, PlaylistVideoAdd, ReorderRequest, Video
)
from ..services.storage import upload_playlist_image

router = APIRouter()

PL_FIELDS = "id, name, image_url, created_at, updated_at, hide_playlist"

VIDEO_FIELDS = """
    v.id, v.title, v.artist, v.record_label, v.originalreleasedate, v.partner_account,
    v.video_url, v.thumbnail_url, v.album_artwork, v.is_active, v.ready_for_mux_delete,
    v.clip_start_ms, v.clip_end_ms, v.duration, v.genre, v.video_id::text, v.link_out
"""


@router.get("", response_model=List[Playlist])
async def list_playlists():
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""SELECT p.id, p.name, p.image_url, p.created_at, p.updated_at, p.hide_playlist,
                       COUNT(pv.id)::int AS video_count
                FROM playlist p
                LEFT JOIN playlist_video pv ON pv.playlist_id = p.id
                WHERE p.hide_playlist = FALSE
                GROUP BY p.id
                ORDER BY p.updated_at DESC NULLS LAST, p.id DESC"""
        )
    return [Playlist(**dict(r)) for r in rows]


@router.post("", response_model=Playlist, status_code=201)
async def create_playlist(
    name: str = Form(...),
    image: Optional[UploadFile] = File(None),
):
    image_url = None
    image_s3_key = None

    if image:
        image_url, image_s3_key = await upload_playlist_image(image)

    pool = get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"""INSERT INTO playlist (name, image_url, image_s3_key)
                VALUES ($1, $2, $3) RETURNING {PL_FIELDS}""",
            name, image_url, image_s3_key
        )
    return Playlist(**dict(row))


@router.get("/containing/{video_id}", response_model=List[int])
async def playlists_containing_video(video_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT playlist_id FROM playlist_video WHERE video_id = $1", video_id
        )
    return [r["playlist_id"] for r in rows]


@router.get("/{playlist_id}", response_model=PlaylistDetail)
async def get_playlist(playlist_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        pl_row = await conn.fetchrow(
            f"SELECT {PL_FIELDS} FROM playlist WHERE id = $1", playlist_id
        )
        if not pl_row:
            raise HTTPException(status_code=404, detail="Playlist not found")

        video_rows = await conn.fetch(
            f"""SELECT
                pv.id          AS pv_id,
                pv.playlist_id AS pv_playlist_id,
                pv.video_id    AS pv_video_id,
                pv."order"     AS pv_order,
                v.id           AS v_id,
                v.title, v.artist, v.record_label, v.originalreleasedate,
                v.partner_account, v.video_url, v.thumbnail_url, v.album_artwork,
                v.is_active, v.ready_for_mux_delete, v.clip_start_ms, v.clip_end_ms,
                v.duration, v.genre, v.video_id::text AS v_video_id, v.link_out
               FROM playlist_video pv
               JOIN video v ON v.id = pv.video_id
               WHERE pv.playlist_id = $1
               ORDER BY pv."order" ASC, pv.id ASC""",
            playlist_id
        )

    pv_items = []
    for r in video_rows:
        d = dict(r)
        video = Video(
            id=d["v_id"], title=d.get("title"), artist=d.get("artist"),
            record_label=d.get("record_label"),
            originalreleasedate=d.get("originalreleasedate"),
            partner_account=d.get("partner_account"),
            video_url=d.get("video_url"), thumbnail_url=d.get("thumbnail_url"),
            album_artwork=d.get("album_artwork"), is_active=d.get("is_active"),
            ready_for_mux_delete=d.get("ready_for_mux_delete"),
            clip_start_ms=d.get("clip_start_ms"), clip_end_ms=d.get("clip_end_ms"),
            duration=d.get("duration"), genre=d.get("genre"),
            video_id=d.get("v_video_id"), link_out=d.get("link_out"),
        )
        pv_items.append(PlaylistVideoItem(
            id=d["pv_id"], playlist_id=d["pv_playlist_id"],
            video_id=d["pv_video_id"], order=d["pv_order"], video=video,
        ))

    return PlaylistDetail(
        id=pl_row["id"], name=pl_row["name"], image_url=pl_row["image_url"],
        created_at=pl_row["created_at"], updated_at=pl_row["updated_at"],
        videos=pv_items,
    )


@router.patch("/{playlist_id}", response_model=Playlist)
async def update_playlist(
    playlist_id: int,
    name: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    pool = get_pool()
    sets = ["updated_at = NOW()"]
    params: list = []
    idx = 1

    if name is not None:
        sets.append(f"name = ${idx}")
        params.append(name)
        idx += 1

    if image:
        image_url, image_s3_key = await upload_playlist_image(image)
        sets.append(f"image_url = ${idx}")
        params.append(image_url)
        idx += 1
        sets.append(f"image_s3_key = ${idx}")
        params.append(image_s3_key)
        idx += 1

    params.append(playlist_id)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            f"UPDATE playlist SET {', '.join(sets)} WHERE id = ${idx} RETURNING {PL_FIELDS}",
            *params
        )
    if not row:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return Playlist(**dict(row))


@router.post("/{playlist_id}/archive", status_code=204)
async def archive_playlist(playlist_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE playlist SET hide_playlist = TRUE WHERE id = $1", playlist_id
        )
    if result == "UPDATE 0":
        raise HTTPException(status_code=404, detail="Playlist not found")


@router.delete("/{playlist_id}", status_code=204)
async def delete_playlist(playlist_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute("DELETE FROM playlist WHERE id = $1", playlist_id)
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Playlist not found")


@router.post("/{playlist_id}/videos", status_code=201)
async def add_video_to_playlist(playlist_id: int, body: PlaylistVideoAdd):
    pool = get_pool()
    async with pool.acquire() as conn:
        max_order = await conn.fetchval(
            'SELECT COALESCE(MAX("order"), -1) FROM playlist_video WHERE playlist_id = $1',
            playlist_id
        )
        try:
            row = await conn.fetchrow(
                'INSERT INTO playlist_video (playlist_id, video_id, "order") VALUES ($1, $2, $3) RETURNING id',
                playlist_id, body.video_id, max_order + 1
            )
        except Exception:
            raise HTTPException(status_code=409, detail="Video already in playlist")
    return {"id": row["id"]}


@router.delete("/{playlist_id}/videos/{video_id}", status_code=204)
async def remove_video_from_playlist(playlist_id: int, video_id: int):
    pool = get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM playlist_video WHERE playlist_id = $1 AND video_id = $2",
            playlist_id, video_id
        )
    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="Video not in playlist")


@router.patch("/{playlist_id}/videos/reorder", status_code=200)
async def reorder_playlist_videos(playlist_id: int, body: ReorderRequest):
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for item in body.items:
                await conn.execute(
                    'UPDATE playlist_video SET "order" = $1 WHERE playlist_id = $2 AND video_id = $3',
                    item.order, playlist_id, item.video_id
                )
    return {"ok": True}
