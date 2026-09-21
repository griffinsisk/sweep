"""Stateless session: Google tokens encrypted into an httpOnly cookie.

Nothing is persisted server-side. Losing the cookie == signed out.
"""
import json
from dataclasses import asdict, dataclass

from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException, Request, Response

from .config import settings

COOKIE_NAME = "sweep_session"
_fernet = Fernet(settings.session_secret.encode())


@dataclass
class Session:
    access_token: str
    refresh_token: str | None
    email: str


def write_session(response: Response, session: Session) -> None:
    blob = _fernet.encrypt(json.dumps(asdict(session)).encode()).decode()
    response.set_cookie(
        COOKIE_NAME,
        blob,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")


def read_session(request: Request) -> Session:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        raise HTTPException(401, "Not signed in")
    try:
        data = json.loads(_fernet.decrypt(raw.encode()))
    except (InvalidToken, ValueError):
        raise HTTPException(401, "Session invalid — sign in again")
    return Session(**data)
