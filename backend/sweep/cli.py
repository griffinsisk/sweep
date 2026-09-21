"""`sweep` command: start the local server and open the browser."""
import sys
import threading
import webbrowser

import uvicorn
from pydantic import ValidationError


def main() -> None:
    try:
        from .config import settings
    except ValidationError as e:  # missing GOOGLE_CLIENT_ID / SECRET
        print(f"Sweep is not configured: {e}", file=sys.stderr)
        print(
            "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in the environment or in a .env "
            "file in the current directory. See SETUP.md.",
            file=sys.stderr,
        )
        sys.exit(1)

    url = settings.base_url
    print(f"Sweep running at {url}  (Ctrl-C to stop)")
    threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    uvicorn.run("sweep.main:app", host="127.0.0.1", port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
