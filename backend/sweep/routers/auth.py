import secrets
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse

from ..config import settings
from ..google import exchange_code, get_email
from ..session import Session, clear_session, read_session, write_session

router = APIRouter(prefix="/auth", tags=["auth"])

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
STATE_COOKIE = "sweep_oauth_state"


@router.get("/login")
async def login():
    state = secrets.token_urlsafe(24)
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.redirect_uri,
        "response_type": "code",
        "scope": " ".join(settings.scopes),
        "access_type": "offline",  # get a refresh token
        "prompt": "consent",
        "state": state,
    }
    resp = RedirectResponse(f"{AUTH_URL}?{urlencode(params)}")
    resp.set_cookie(STATE_COOKIE, state, httponly=True, samesite="lax", max_age=600, path="/")
    return resp


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None,
                   error: str | None = None):
    if error:
        raise HTTPException(400, f"Google returned an error: {error}")
    if not code or not state or state != request.cookies.get(STATE_COOKIE):
        raise HTTPException(400, "Invalid OAuth state")

    tokens = await exchange_code(code)
    email = await get_email(tokens["access_token"])
    session = Session(
        access_token=tokens["access_token"],
        refresh_token=tokens.get("refresh_token"),
        email=email,
    )
    resp = RedirectResponse(settings.after_login_url)
    write_session(resp, session)
    resp.delete_cookie(STATE_COOKIE, path="/")
    return resp


@router.get("/me")
async def me(session: Session = Depends(read_session)):
    return {"email": session.email}


@router.post("/logout")
async def logout():
    resp = RedirectResponse(settings.after_login_url, status_code=303)
    clear_session(resp)
    return resp
