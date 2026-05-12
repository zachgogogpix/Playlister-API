from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import date, datetime


class Video(BaseModel):
    id: int
    title: Optional[str]
    artist: Optional[str]
    record_label: Optional[str]
    originalreleasedate: Optional[date]
    partner_account: Optional[str]
    video_url: Optional[str]
    thumbnail_url: Optional[str]
    album_artwork: Optional[str]
    is_active: Optional[bool]
    ready_for_mux_delete: Optional[bool]
    clip_start_ms: Optional[int]
    clip_end_ms: Optional[int]
    duration: Optional[int]
    genre: Optional[str]
    video_id: Optional[str]
    link_out: Optional[str]

    @field_validator('duration', mode='before')
    @classmethod
    def coerce_duration(cls, v):
        if v is None:
            return None
        return int(round(float(v)))

    class Config:
        from_attributes = True


class VideoListResponse(BaseModel):
    videos: List[Video]
    total: int
    page: int
    limit: int
    pages: int


class ClipUpdate(BaseModel):
    clip_start_ms: int
    clip_end_ms: int


class FlagsUpdate(BaseModel):
    is_active: Optional[bool] = None
    ready_for_mux_delete: Optional[bool] = None


class PlaylistCreate(BaseModel):
    name: str


class PlaylistUpdate(BaseModel):
    name: Optional[str] = None


class Playlist(BaseModel):
    id: int
    name: str
    image_url: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    video_count: Optional[int] = 0
    hide_playlist: Optional[bool] = False

    class Config:
        from_attributes = True


class PlaylistVideoItem(BaseModel):
    id: int
    playlist_id: int
    video_id: int
    order: Optional[int] = 0
    video: Optional[Video] = None


class PlaylistDetail(BaseModel):
    id: int
    name: str
    image_url: Optional[str]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    videos: List[PlaylistVideoItem] = []


class PlaylistVideoAdd(BaseModel):
    video_id: int


class ReorderItem(BaseModel):
    video_id: int
    order: int


class ReorderRequest(BaseModel):
    items: List[ReorderItem]
