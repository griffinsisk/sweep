from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .routers import ai, auth, cleanup, senders

app = FastAPI(
    title="Sweep",
    description="Bulk Gmail cleanup. Nothing stored server-side.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(cleanup.router)
app.include_router(senders.router)
app.include_router(ai.router)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
