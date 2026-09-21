# sweep — memory

## Rulings
- **Sep 21 · Self-hosted, not hosted.** `gmail.modify` is a restricted scope; a hosted copy is capped at 100 test users until it passes Google verification plus an annual CASA Tier 2 assessment. Local run avoids all of it and gives a stronger privacy story.
- **Sep 21 · Direct Gmail REST for the core, not an MCP-driven agent.** The speed claim rests on batchModify at 1,000 per call; per-message agent tool calls would be slower than Gmail's UI. Claude stays in the bounded triage role. An MCP server over Sweep's own primitives is the second front door, after the app works.
- **Sep 21 · OAuth client type is Desktop app.** Loopback redirect needs no registration; Google treats the desktop secret as non-confidential.
- **Sep 21 · Session key is generated at startup when unset.** On a laptop, restart equals sign in again. Nothing is persisted.
- **Sep 21 · ruff rules pinned to E4, E7, E9, F, I.** ruff 0.16 widened its defaults and flagged FastAPI's `Depends` idiom; the pin keeps local and CI identical.

## Lessons
- **The `sweep` folder was never its own repo.** Git root resolved to the home directory. Baseline commit e651206 captured the old split layout before restructuring.

## Sessions
### 2026-09-21
Landed
- Python package renamed `app` → `sweep`, `sweep` console script starts uvicorn on 127.0.0.1 and opens the browser — `sweep/cli.py`, wheel `sweep_gmail-0.2.0-py3-none-any.whl` built with `uv build`
- FastAPI serves `sweep/static/` with SPA fallback; Vite builds into that folder — TestClient: `/` 200 html, `/some/spa/route` 200 html, `/assets/*` 200, `/auth/login` 307 with `redirect_uri=http://127.0.0.1:8000/auth/callback`
- Only GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET required; SESSION_SECRET auto-generated; FRONTEND_ORIGIN only for Vite dev — `sweep/config.py`
- `/auth/me` returns `ai_enabled`; UI hides the Claude button and shows a hint when no Anthropic key — `App.tsx`
- Dockerfile and deploy docs removed; README, SETUP, PLAN, PRIVACY, `.env.example`, CI rewritten for the local install; CI builds wheel and releases on `v*` tags
- `ruff check` clean, `pytest` 6 passed
Did not land
- Live OAuth round-trip on the new build — sandbox blocks binding a local port; needs Griffin's browser and Google project
- GitHub remote and v0.2.0 tag — release install URLs in the docs are aspirational until then
Surfaced
- setuptools refuses `readme = "../README.md"` outside the package root; dropped the readme field
- `python -m build` fails inside a uv venv (no pip for build isolation); `uv build --wheel` works and is what CI should probably use too
