# Sweep

Clear out years of Gmail in minutes, not hours.

Gmail's web UI caps bulk actions at 50 conversations per click. Sweep uses the Gmail API's `batchModify` endpoint (1,000 messages per request) to trash tens of thousands of messages in a few dozen calls, groups the rest by sender so you can see who's actually filling your inbox, and optionally asks Claude to suggest what to keep, unsubscribe from, or trash.

It runs on your own machine. One command starts a local server and opens your browser. Nothing is stored anywhere: your Gmail token lives in an encrypted, httpOnly cookie and is gone when you sign out.

## What it does

- **Presets** — one click for the big wins: everything before a cutoff date, attachments over 10 MB, promotions older than a year, and so on
- **Senders** — the top senders in your mailbox by message count, with a real unsubscribe link pulled from each message's `List-Unsubscribe` header
- **Suggestions** — Claude reads the sender list (domain, count, a few subject lines) and labels each keep / unsubscribe / trash with a one-line reason. You confirm; it never acts alone
- **Empty trash** — because moving to trash doesn't free storage. Hard confirmation required
- **Storage gauge** — live quota from Google, plus "freed this session"

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

Pre-alpha. Built in the open. See [PLAN.md](PLAN.md) for milestones.

## License

MIT
