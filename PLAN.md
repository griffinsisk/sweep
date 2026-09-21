# Plan

## The problem

15 GB Gmail quota, 14.7 GB used, ~60,000 messages. The web UI can only select 50 conversations at a time and each bulk action has several seconds of latency. Deleting everything before 2020 by hand would take hours.

## v1 — "done" means

- [x] One command installs and runs it locally; the only external setup is the Google Cloud project
- [x] Sign in with Google, see storage used / total
- [x] Run any preset: exact streamed count with size estimate and preview, trash in batches of 1,000 via `batchModify`
- [x] Build a custom query without knowing Gmail syntax
- [x] Undo or permanently delete any single action; review it in Gmail
- [x] Senders view: top 50 senders by count, trash-all per sender, unsubscribe link where present
- [x] Claude suggestions per sender (keep / unsubscribe / trash + reason), applied only on confirmation — built, not yet exercised with a live key
- [x] Empty trash with a typed confirmation
- [x] "Freed this session" with Google-confirmed figure alongside the estimate
- [x] README and architecture write-up
- [ ] 2-minute demo video

## v1.1 — stop the inflow, not just the storage

The senders view can only trash today. That addresses storage; unsubscribing addresses why the mailbox refills.

- [ ] Senders view: real per-sender totals and a configurable age and sample size — the counts mean what they look like they mean
- [ ] Classify each sender's unsubscribe path from its headers: **one-click** (RFC 8058 `List-Unsubscribe-Post: List-Unsubscribe=One-Click` + https URL, a bare POST does it; Gmail requires this of bulk senders since 2024), **mailto** (`List-Unsubscribe: <mailto:…>`, one empty email does it), or **manual** (https link only, open it yourself)
- [ ] Per-row Unsubscribe button for one-click and mailto senders; the link stays for manual ones
- [ ] Bulk: "Unsubscribe from all N one-click senders" with a checklist to deselect, progress like trash, and Trash all offered as the follow-up on each row
- [ ] Claude's keep / unsubscribe / trash suggestions become actionable: tick the ones it labelled unsubscribe, press one button
- [ ] Report "requested" not "unsubscribed": a 200 means the server accepted the request, not that mail stops. Record the date in the ledger so a later scan can show whether the sender went quiet
- [ ] The mailto path sends email from the user's account for the first time. Separate opt-in in the UI; call it out in PRIVACY.md
- [ ] Claude "anything I should keep?" on a query's preview sample — flags the bank, the school, the doctor hiding inside a promotions query before you trash it
- [ ] First-time-user timing of SETUP.md with screenshots where people stall

## v2 — MCP server

- [ ] `sweep-mcp`: count, trash, senders, untrash, empty-trash tools over the same Gmail session, with the same confirmation gates — Claude Desktop can run "show me who fills my inbox and trash the newsletters older than a year"

## Milestones

| # | Milestone | Proves |
|---|---|---|
| 1 | Scaffold, OAuth round-trip, storage gauge | Token flow works end to end |
| 2 | Presets via `batchModify` | The core speed claim — measure GB freed and minutes taken |
| 3 | Senders view + `List-Unsubscribe` | The thing Gmail's UI can't do |
| 4 | Claude suggestions | Turns a script into an assistant |
| 5 | Polish, docs, demo video | Portfolio deliverables |
| 6 | MCP server over the same primitives | Claude Desktop can drive the cleanup with the same confirmation gates |

Milestones 1–5 shipped in v0.2.0.

## Distribution

**Self-hosted (decided 2026-09-21).** Each user creates their own Google Cloud project and runs Sweep on their own machine with `uv tool install` or `pipx`. The compiled frontend ships inside the Python wheel so nobody needs Node.

**Why not hosted.** Google lets an unverified app run only for up to 100 named test users. Going past that needs verification: a hosted privacy policy and homepage, a demo video of the consent flow, brand verification, and, because a backend would handle Gmail data, a CASA Tier 2 assessment by a Google-approved lab repeated annually. Self-hosting sidesteps all of it and gives a stronger privacy story. Revisit only if there is real demand from people who will not do the 10-minute Google setup.

## v2 backlog

- Custom Gmail query input
- Scheduled cleanups (needs token persistence → real security review)
- Attachment-only stripping (download attachment, re-insert message without it)
- Multi-account
- Export a "what I deleted" CSV before emptying trash

## Non-goals

- Reading message bodies
- Storing anything about the user server-side
- Acting on Claude's suggestions without a click
