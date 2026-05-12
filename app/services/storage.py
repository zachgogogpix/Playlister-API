import os
import uuid
import boto3
from fastapi import UploadFile
from dotenv import load_dotenv

load_dotenv()

BUCKET = os.getenv("DO_SPACES_BUCKET", "prod-vibestream")
REGION = os.getenv("DO_SPACES_REGION", "sfo3")
KEY_ID = os.getenv("DO_SPACES_KEY", "")
SECRET = os.getenv("DO_SPACES_SECRET", "")
ENDPOINT = f"https://{REGION}.digitaloceanspaces.com"
CDN_BASE = f"https://{BUCKET}.{REGION}.cdn.digitaloceanspaces.com"


def _client():
    return boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        aws_access_key_id=KEY_ID,
        aws_secret_access_key=SECRET,
    )


async def upload_playlist_image(file: UploadFile) -> tuple[str, str]:
    ext = os.path.splitext(file.filename or "image.jpg")[1] or ".jpg"
    key = f"playlists/{uuid.uuid4().hex}{ext}"
    content = await file.read()

    _client().put_object(
        Bucket=BUCKET,
        Key=key,
        Body=content,
        ContentType=file.content_type or "image/jpeg",
        ACL="public-read",
    )

    url = f"{CDN_BASE}/{key}"
    return url, key
