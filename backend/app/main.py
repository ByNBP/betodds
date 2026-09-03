"""FastAPI uygulamasi."""
import contextlib
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import db
from .api import router
from .collector import collector
from .config import BASE_DIR

STATIC_DIR = os.environ.get(
    "BETODDS_STATIC", os.path.join(os.path.dirname(BASE_DIR), "frontend", "dist"))


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    if os.environ.get("BETODDS_NO_COLLECTOR") != "1":
        await collector.start()
    try:
        yield
    finally:
        await collector.stop()


app = FastAPI(title="BetOdds", version="0.1.0", lifespan=lifespan,
              description="Mac oncesi bahis oranlarini arsivler, canli veriyi sunar.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(router)

# Frontend build'i varsa ayni porttan servis et (SPA fallback ile).
if os.path.isdir(STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC_DIR, "assets")),
              name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        # Bilinmeyen /api yollari index.html degil, duzgun bir 404 dondursun.
        if full_path.startswith("api/"):
            raise HTTPException(404, "bilinmeyen API ucu")
        candidate = os.path.join(STATIC_DIR, full_path)
        if full_path and os.path.isfile(candidate):
            return FileResponse(candidate)
        return FileResponse(os.path.join(STATIC_DIR, "index.html"))
