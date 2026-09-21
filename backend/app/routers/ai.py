from fastapi import APIRouter, Depends, HTTPException

from .. import ai
from ..session import read_session

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/suggest", response_model=list[ai.Suggestion], dependencies=[Depends(read_session)])
async def suggest(senders: list[ai.SenderIn]):
    if len(senders) > 200:
        raise HTTPException(400, "Send at most 200 senders per request")
    try:
        return await ai.suggest(senders)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
