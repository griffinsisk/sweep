"""Request-scoped Gmail client. If the access token was refreshed during
the request, the updated session is written back to the cookie."""
from collections.abc import AsyncIterator

from fastapi import Depends, Request, Response

from .google import Gmail
from .session import Session, read_session, write_session


async def gmail_client(
    request: Request, response: Response, session: Session = Depends(read_session)
) -> AsyncIterator[Gmail]:
    client = Gmail(session)
    try:
        yield client
    finally:
        if client.token_refreshed:
            write_session(response, client.session)
        await client.close()
