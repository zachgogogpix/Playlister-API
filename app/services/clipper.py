import httpx

JUANSTREAM_URL = "https://callme.juanstream.com/trim-video/"


def _ms_to_timestamp(ms: int) -> str:
    total_s = ms / 1000
    hours = int(total_s // 3600)
    minutes = int((total_s % 3600) // 60)
    seconds = total_s % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}"


async def trim_clip(mp4_url: str, start_ms: int, end_ms: int) -> bytes:
    payload = {
        "url": mp4_url,
        "start": _ms_to_timestamp(start_ms),
        "end": _ms_to_timestamp(end_ms),
    }
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(JUANSTREAM_URL, json=payload)
        resp.raise_for_status()
        return resp.content
