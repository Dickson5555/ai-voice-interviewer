import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routes.websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Voice Interviewer")

# Health check for Render / uptime monitors.
@app.get("/health")
async def health():
    return {"status": "ok"}

# WebSocket + any future API routes MUST be registered before static mount.
app.include_router(ws_router)

# Static SPA at root - keep LAST so it doesn't shadow API routes.
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")

logger.info("AI Voice Interviewer app initialized.")