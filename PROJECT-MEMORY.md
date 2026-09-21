# sweep — memory

## Rulings
- **Sep 21 · Self-hosted, not hosted.** `gmail.modify` is a restricted scope; a hosted copy is capped at 100 test users until it passes Google verification plus an annual CASA Tier 2 assessment. Local run avoids all of it and gives a stronger privacy story.
- **Sep 21 · Direct Gmail REST for the core, not an MCP-driven agent.** The speed claim rests on batchModify at 1,000 per call; per-message agent tool calls would be slower than Gmail's UI. Claude stays in the bounded triage role. An MCP server over Sweep's own primitives is the second front door, after the app works.
- **Sep 21 · OAuth client type is Desktop app.** Loopback redirect needs no registration; Google treats the desktop secret as non-confidential.
- **Sep 21 · Session key is generated at startup when unset.** On a laptop, restart equals sign in again. Nothing is persisted.
- **Sep 21 · ruff rules pinned to E4, E7, E9, F, I.** ruff 0.16 widened its defaults and flagged FastAPI's `Depends` idiom; the pin keeps local and CI identical.

- **Sep 21 · Full Gmail scope, not gmail.modify.** batchDelete is the one call gmail.modify cannot make; Empty trash and Delete forever need it.
- **Sep 21 · All sizes use 2^30 and say GB.** Gmail does the same; matching it beats being technically right.
- **Sep 21 · A ledger session is one calendar day per account.** Page loads and restarts are not sessions.
- **Sep 21 · Every Sweep-computed number carries ≈; numbers from Google do not.**

## Lessons
- **Guessing from symptoms cost two wrong fixes on the 204 bug.** Log the failing response (status, headers, body head) before theorizing; `Gmail.describe_last` now does this on JSON failures.
- **The `sweep` folder was never its own repo.** Git root resolved to the home directory. Baseline commit e651206 captured the old split layout before restructuring.

## Sessions
### 2026-09-21
Landed
- Public repo github.com/griffinsisk/sweep, v0.2.0 released with `sweep_gmail-0.2.0-py3-none-any.whl` (75,905 bytes) attached by CI; SETUP.md latest-release URL returns 200 — tag had to be re-pushed once, the first push right after repo creation fired no workflow
- Live end-to-end on Griffin's Gmail: Desktop OAuth client + loopback redirect signs in; counts, trash, undo, Delete forever all ran; Google confirmed ~4.7 GB freed
- Query builder (age/kind/size → editable Gmail query), Customize links on presets, presets swapped (drop 25MB, add forums + unsubscribe) — `App.tsx` QueryBuilder
- Count streams NDJSON per 500-id page, capped at 100 pages (50,000+), final line carries avg_bytes + preview from a 100-message even-spread sample — `Gmail.count_stream`, 20 tests
- Trash/untrash/delete stream two-phase progress; batch calls 3 in flight (50 units each vs 250/sec quota) — `Gmail._batch_stream`
- Trash log under Empty trash with per-action Undo, Delete forever, Review in Gmail (authuser=email) — `EmptyTrash`
- Scope widened to https://mail.google.com/ (batchDelete refuses gmail.modify); 403 insufficientPermissions → "sign out and back in" message
- Sizes divide by 2^30 to match Gmail's display; legend shows ≈estimate vs Google-confirmed; per-day localStorage ledger — `ledger.ts`
- Gmail 204 No Content on messages.list with a fields mask = zero matches; mapped to {} in `Gmail._json` (found via response-context logging, after two wrong guesses)
Did not land
- Ledger cannot backfill the ~4.7 GB freed before it existed; a manual starting-figure knob was offered and not built
Surfaced
- resultSizeEstimate saturates ~201; never use it for counts
- Stop in the browser did not stop the server stream; fixed with request.is_disconnected() per line
- Empty 200 bodies from Gmail under load; retried with backoff, then reported as rate limit
- ruff 0.16 widened defaults (B008 on FastAPI Depends); rules pinned to E4/E7/E9/F/I
- setuptools rejects readme outside package root; `python -m build` needs pip in the venv, `uv build --wheel` does not
