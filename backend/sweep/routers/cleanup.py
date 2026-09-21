import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import gmail_client
from ..google import Gmail
from ..presets import PRESET_INDEX, PRESETS
from ..session import read_session

log = logging.getLogger("sweep")

router = APIRouter(prefix="/api", tags=["cleanup"])


@router.get("/storage")
async def storage(gmail: Gmail = Depends(gmail_client)):
    profile, quota = await gmail.profile(), await gmail.storage_quota()
    return {"messagesTotal": profile.get("messagesTotal"), "quota": quota}


@router.get("/presets")
async def list_presets():
    return PRESETS


def _ndjson(request: Request, what: str, open) -> StreamingResponse:
    """Stream an async generator of dicts as NDJSON. Manages its own Gmail
    client because the response body runs after request-scoped dependencies
    have exited. Errors become a final line, never a broken stream."""
    session = read_session(request)

    async def body():
        gmail = Gmail(session)
        try:
            async for line in open(gmail):
                yield json.dumps(line) + "\n"
        except HTTPException as e:
            log.error("%s failed: %s", what, e.detail)
            yield json.dumps({"error": e.detail, "done": True}) + "\n"
        except ValueError:  # Google answered 200 with a body that is not JSON
            log.warning("%s hit an unparseable Google response", what)
            msg = "Google sent an unreadable response partway through. Try again."
            yield json.dumps({"error": msg, "done": True}) + "\n"
        except Exception as e:  # anything else must still reach the UI as a line
            log.exception("%s crashed", what)
            yield json.dumps({"error": f"{type(e).__name__}: {e}", "done": True}) + "\n"
        finally:
            await gmail.close()

    return StreamingResponse(body(), media_type="application/x-ndjson")


def _count_stream(request: Request, query: str) -> StreamingResponse:
    return _ndjson(request, f"count {query!r}", lambda g: g.count_stream(query))


@router.get("/presets/{key}/count")
async def preset_count(key: str, request: Request):
    preset = PRESET_INDEX.get(key) or _404(key)
    return _count_stream(request, preset.query)


@router.post("/presets/{key}/trash")
async def preset_trash(key: str, request: Request):
    """NDJSON: listing progress, then trashing progress, then a final line
    with the ids so the browser can undo. 60k messages is ~120 list calls
    and 60 batchModify calls, three at a time."""
    preset = PRESET_INDEX.get(key) or _404(key)
    return _ndjson(request, f"trash {preset.query!r}", lambda g: g.trash_stream(preset.query))


class QueryBody(BaseModel):
    query: str


@router.post("/query/count")
async def query_count(body: QueryBody, request: Request):
    return _count_stream(request, body.query)


@router.post("/query/trash")
async def query_trash(body: QueryBody, request: Request):
    return _ndjson(request, f"trash {body.query!r}", lambda g: g.trash_stream(body.query))


class IdsBody(BaseModel):
    ids: list[str]


class DeleteBody(IdsBody):
    confirm: str  # must equal "DELETE FOREVER"


@router.post("/untrash")
async def untrash(body: IdsBody, request: Request):
    """Reverse a trash action: the ids come back from the browser that ran it."""
    if len(body.ids) > 100_000:
        raise HTTPException(400, "Too many ids in one undo")
    return _ndjson(request, "untrash", lambda g: g.untrash_stream(body.ids))


@router.post("/delete")
async def delete_ids(body: DeleteBody, request: Request):
    """Permanently delete one earlier trash action's messages. Irreversible."""
    if body.confirm != "DELETE FOREVER":
        raise HTTPException(400, 'Type "DELETE FOREVER" to confirm')
    if len(body.ids) > 100_000:
        raise HTTPException(400, "Too many ids in one delete")
    return _ndjson(request, "delete", lambda g: g.delete_stream(body.ids))


def _404(key: str):
    raise HTTPException(404, f"Unknown preset: {key}")
