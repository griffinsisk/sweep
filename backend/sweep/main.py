from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .routers import auth, cleanup

STATIC = Path(__file__).parent / "static"

app = FastAPI(
    title="Sweep",
    description="Bulk Gmail cleanup. Runs on your machine; nothing stored anywhere.",
    version="0.3.0",
)

if settings.frontend_origin:  # Vite dev server on another origin
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(cleanup.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}


# Built frontend, when present. Everything not matched above falls through
# to index.html so the single-page app owns the URL space.
if (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    async def spa(path: str):
        candidate = STATIC / path
        if path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STATIC / "index.html")
