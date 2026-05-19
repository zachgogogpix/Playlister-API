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


async def enable_mp4_support(asset_id: str) -> str:
    """
    Enable MP4 support for a Mux asset.

    Returns:
        "already_ready" - Asset is already prepared, skip waiting
        "enabled" - MP4 support was just enabled, needs wait
        "already_enabled" - MP4 support was already enabled, needs wait
    """
    async with httpx.AsyncClient() as client:
        resp = await client.put(
            f"{MUX_BASE}/assets/{asset_id}/mp4-support",
            json={"mp4_support": "capped-1080p"},
            auth=_auth(),
            timeout=30,
        )

        # 200/201: Successfully enabled
        if resp.status_code in (200, 201):
            return "enabled"

        # 409: Already enabled
        if resp.status_code == 409:
            return "already_enabled"

        # 400: Asset is already prepared or MP4 support already exists
        if resp.status_code == 400:
            try:
                error_data = resp.json()
                error_msg = str(error_data).lower()
                # If MP4 support is already configured or asset is already prepared
                if "invalid" in error_msg or "mp4" in error_msg or "support" in error_msg:
                    return "already_ready"
            except:
                pass

        # Other errors: raise
        resp.raise_for_status()
        return "enabled"


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
