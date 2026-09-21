# Sweep

Clear out years of Gmail in minutes, not hours.

Gmail's web UI caps bulk actions at 50 conversations per click. Sweep uses the Gmail API's `batchModify` endpoint (1,000 messages per request) to trash tens of thousands of messages in a few dozen calls, groups the rest by sender so you can see who's actually filling your inbox, and asks Claude to suggest what to keep, unsubscribe from, or trash.

Nothing is stored server-side. Your Gmail token lives in an encrypted, httpOnly cookie and is gone when you sign out.

## What it does

- **Presets** — one click for the big wins: everything before a cutoff date, attachments over 10 MB, promotions older than a year, and so on
- **Senders** — the top senders in your mailbox by message count, with a real unsubscribe link pulled from each message's `List-Unsubscribe` header
- **Suggestions** — Claude reads the sender list (domain, count, a few subject lines) and labels each keep / unsubscribe / trash with a one-line reason. You confirm; it never acts alone
- **Empty trash** — because moving to trash doesn't free storage. Hard confirmation required
- **Storage gauge** — live quota from Google, plus "freed this session"

## Architecture

```
frontend/   Vite + React + TypeScript      → static site (Vercel / Netlify / Pages)
backend/    FastAPI                        → Fly.io / Render / Railway
```

Flow:

1. Browser hits `/auth/login` → redirected to Google's consent screen
2. Google redirects to `/auth/callback` → backend exchanges the code for tokens
3. Tokens are encrypted (Fernet) into an httpOnly cookie. No database
4. Frontend calls `/api/*`; backend decrypts the cookie, calls Gmail REST, refreshes the token on 401
5. `/api/ai/suggest` sends **only** sender domain, count, and up to 3 subject lines to Claude — never bodies, never recipients

### Why a backend at all?

The Anthropic key can't live in the browser. Once there's a server, doing the OAuth code exchange there too (with the client secret) is the more secure option. The tradeoff: a server that touches Gmail data means Google's CASA security assessment applies if this is ever verified for public use. See [PLAN.md](PLAN.md) for the go-live path.

## Scopes requested

| Scope | Why |
|---|---|
| `gmail.modify` | list, trash, and permanently delete messages |
| `drive.metadata.readonly` | read storage quota for the gauge (optional — drop it and the gauge falls back to message counts) |
| `openid email` | show which account is signed in |

## Local development

Prereqs: Python 3.11+, Node 20+, a Google Cloud project with the Gmail API enabled and an OAuth 2.0 Web client.

```bash
cp .env.example backend/.env         # fill in Google + Anthropic credentials
cd backend && pip install -e ".[dev]" && uvicorn app.main:app --reload
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. In Google Cloud Console, add `http://localhost:8000/auth/callback` as an authorized redirect URI and add your own Gmail address as a **test user** on the OAuth consent screen.

## Status

Pre-alpha. Built in the open. See [PLAN.md](PLAN.md) for milestones.

## License

MIT
