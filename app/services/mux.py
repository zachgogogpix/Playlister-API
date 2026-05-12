import asyncio
import os
import re
import httpx
from dotenv import load_dotenv

load_dotenv()

MUX_BASE = "https://api.mux.com/video/v1"


def _auth():
    return (os.getenv("MUX_TOKEN_ID", ""), os.getenv("MUX_TOKEN_SECRET", ""))


def extract_playback_id(video_url: str) -> str:
    match = re.search(r"stream\.mux\.com/([^./]+)", video_url)
    return match.group(1) if match else ""


def build_mp4_url(playback_id: str) -> str:
    return f"https://stream.mux.com/{playback_id}/capped-1080p.mp4"


async def enable_mp4_support(asset_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{MUX_BASE}/assets/{asset_id}/mp4-support",
            json={"mp4_support": "capped-1080p"},
            auth=_auth(),
            timeout=30,
        )
        if resp.status_code not in (200, 201, 409):
            resp.raise_for_status()


async def wait_for_mp4_ready(asset_id: str, poll_interval: float = 4.0, timeout: float = 300.0):
    elapsed = 0.0
    async with httpx.AsyncClient() as client:
        while elapsed < timeout:
            resp = await client.get(f"{MUX_BASE}/assets/{asset_id}", auth=_auth(), timeout=30)
            resp.raise_for_status()
            data = resp.json().get("data", {})
            static = data.get("static_renditions", {})
            if static.get("status") == "ready":
                return
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
    raise TimeoutError(f"Mux MP4 not ready after {timeout}s for asset {asset_id}")
