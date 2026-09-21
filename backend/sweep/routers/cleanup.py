from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import gmail_client
from ..google import Gmail
from ..presets import PRESET_INDEX, PRESETS

router = APIRouter(prefix="/api", tags=["cleanup"])


@router.get("/storage")
async def storage(gmail: Gmail = Depends(gmail_client)):
    profile, quota = await gmail.profile(), await gmail.storage_quota()
    return {"messagesTotal": profile.get("messagesTotal"), "quota": quota}


@router.get("/presets")
async def list_presets():
    return PRESETS


@router.get("/presets/{key}/count")
async def preset_count(key: str, gmail: Gmail = Depends(gmail_client)):
    preset = PRESET_INDEX.get(key) or _404(key)
    return await gmail.count(preset.query)


class TrashResult(BaseModel):
    trashed: int
    query: str


@router.post("/presets/{key}/trash", response_model=TrashResult)
async def preset_trash(key: str, gmail: Gmail = Depends(gmail_client)):
    """List every matching id, then trash in 1,000-message batches.
    60k messages ≈ 120 list calls + 60 batchModify calls."""
    preset = PRESET_INDEX.get(key) or _404(key)
    ids = await gmail.list_message_ids(preset.query)
    n = await gmail.trash(ids)
    return TrashResult(trashed=n, query=preset.query)


class QueryBody(BaseModel):
    query: str


@router.post("/query/count")
async def query_count(body: QueryBody, gmail: Gmail = Depends(gmail_client)):
    return await gmail.count(body.query)


@router.post("/query/trash", response_model=TrashResult)
async def query_trash(body: QueryBody, gmail: Gmail = Depends(gmail_client)):
    ids = await gmail.list_message_ids(body.query)
    n = await gmail.trash(ids)
    return TrashResult(trashed=n, query=body.query)


class EmptyTrashBody(BaseModel):
    confirm: str  # must equal "DELETE FOREVER"


@router.post("/trash/empty")
async def empty_trash(body: EmptyTrashBody, gmail: Gmail = Depends(gmail_client)):
    """Permanently delete everything in Trash. This is the step that
    actually frees storage — and the one you can't undo."""
    if body.confirm != "DELETE FOREVER":
        raise HTTPException(400, 'Type "DELETE FOREVER" to confirm')
    ids = await gmail.list_message_ids("in:trash")
    n = await gmail.delete_forever(ids)
    return {"deleted": n}


def _404(key: str):
    raise HTTPException(404, f"Unknown preset: {key}")
