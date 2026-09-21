# Sweep

Clear out years of Gmail in minutes, not hours.

Gmail's web UI caps bulk actions at 50 conversations per click. Sweep uses the Gmail API's `batchModify` endpoint (1,000 messages per request) to trash tens of thousands of messages in a few dozen calls, groups the rest by sender so you can see who's actually filling your inbox, and optionally asks Claude to suggest what to keep, unsubscribe from, or trash.

It runs on your own machine. One command starts a local server and opens your browser. Nothing is stored anywhere: your Gmail token lives in an encrypted, httpOnly cookie and is gone when you sign out.

## What it does

- **Presets** — one click for the big wins: everything before 2020, attachments over 10 MB, promotions, social, updates, mailing lists, and no-reply senders older than a year. Each is a plain Gmail search you can paste into Gmail to check first
- **Build your own** — pick an age (3 months to 5 years, or before a date), a kind of mail, and a size; Sweep writes the Gmail search and lets you edit it. Any preset can be loaded into the builder with one click
- **Count before you act** — an exact count streams in as it runs, with an estimated size and a preview of who sent the mail, the date range, and a few subjects, all from a 100-message sample. Counts cap at 50,000+ so nothing spins forever
- **Trash with a progress bar** — two phases, finding and moving, with a running count. Batches of 1,000, three in flight
- **Undo and per-action delete** — every trash action lands in a log with its count, size, an Undo button, a Delete forever button, and a Review in Gmail link scoped to exactly what it moved
- **Senders** — a sample of your older mail grouped by sender, with a real unsubscribe link pulled from each message's `List-Unsubscribe` header
- **Suggestions** — Claude reads the sender list (domain, count, a few subject lines) and labels each keep / unsubscribe / trash with a one-line reason. You confirm; it never acts alone. Off unless you set an Anthropic key
- **Empty trash** — because moving to trash doesn't free storage. Typed confirmation required
- **Storage gauge** — Google's quota in the same units Gmail shows, an estimated figure for what you freed, and what Google has confirmed since you signed in. Returning users see a per-day history kept in the browser

Every number Sweep computed carries a ≈. Numbers without one come from Google.

## Quick start

You need a Google Cloud project of your own (about 10 minutes, one time) because Google restricts the Gmail scope Sweep uses. [SETUP.md](SETUP.md) walks through it. Then:

```bash
uv tool install https://github.com/griffinsisk/sweep/releases/latest/download/sweep_gmail-0.2.0-py3-none-any.whl
export GOOGLE_CLIENT_ID=... GOOGLE_CLIENT_SECRET=...
sweep
```

## Architecture

One Python process. FastAPI serves the API and the compiled React frontend from the same port on `127.0.0.1`.

```
backend/    FastAPI + the `sweep` command       python package, ships the built UI
frontend/   Vite + React + TypeScript            builds into backend/sweep/static/
```

Flow:

1. `sweep` starts uvicorn on 127.0.0.1 and opens the browser
2. Sign in redirects to Google's consent screen and back to `/auth/callback`
3. Tokens are encrypted with a key generated at startup into an httpOnly cookie. No database, no files
4. The UI calls `/api/*`; the server decrypts the cookie, calls Gmail REST, refreshes the token on 401
5. `/api/ai/suggest` sends **only** sender domain, count, and up to 3 subject lines to Claude. Never bodies, never recipients. Off unless you set an Anthropic key

### Why self-hosted?

The full Gmail scope is a restricted scope. A hosted copy would serve at most 100 named test users until it passed Google's verification, which for an app whose server touches Gmail data means an annual CASA security assessment. Running locally means anyone can use it today, the tokens never leave their machine, and the verification question goes away. See [PLAN.md](PLAN.md).

## Scopes requested

| Scope | Why |
|---|---|
| `https://mail.google.com/` | list, trash, and permanently delete messages. Permanent deletion is the reason for the full scope; `gmail.modify` cannot do it |
| `drive.metadata.readonly` | read storage quota for the gauge (optional — drop it and the gauge falls back to message counts) |
| `openid email` | show which account is signed in |

## Developing

See the Developing section of [SETUP.md](SETUP.md).

## Status

**v0.2.0.** Runs end to end on a real mailbox: sign-in, counts, trash, undo, permanent delete, with Google confirming several GB freed. See [PLAN.md](PLAN.md) for what is next, including an MCP server so Claude Desktop can drive a cleanup through the same confirmation gates.

## License

MIT
