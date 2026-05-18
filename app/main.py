from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import os
from dotenv import load_dotenv

from .database import init_pool, close_pool, create_tables
from .routers import videos, playlists, clips

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_pool()
    await create_tables()
    yield
    await close_pool()


app = FastAPI(title="Vibe Stream API", version="1.3.0", lifespan=lifespan)

# Get UI origin from environment variable
ui_origin = os.getenv("UI_ORIGIN", "http://localhost:5173")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[ui_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(videos.router, prefix="/api/videos", tags=["videos"])
app.include_router(playlists.router, prefix="/api/playlists", tags=["playlists"])
app.include_router(clips.router, prefix="/api/clips", tags=["clips"])

clips_dir = os.path.join(os.path.dirname(__file__), "..", "clips")
os.makedirs(clips_dir, exist_ok=True)
app.mount("/clips", StaticFiles(directory=clips_dir), name="clips")


@app.get("/")
async def root():
    return {"service": "Vibe Stream API", "version": "1.3.0"}
