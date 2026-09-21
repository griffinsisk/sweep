---
name: sweep
direction: >
  A portfolio-grade Gmail cleanup tool anyone can install and run on their own machine
  in one command, with a Claude-assisted sender triage and, later, an MCP server over the
  same primitives.
agent: claude
health: on-track
updated: 2026-09-21
evidence: strong
written: unattended
---

## Where it stands
Sweep runs as one local Python process serving its own UI, installed from a wheel, and is public at github.com/griffinsisk/sweep with v0.2.0 tagged. Griffin has run it end to end on his own mailbox: sign-in, counts, trash, undo, permanent delete, with Google confirming several GB freed. Today's session added a query builder, streamed counts with size estimates and previews, per-action undo and delete, progress bars, and a per-day history ledger. The consent-screen walk-through is verified against Google's current console. The MCP server is the next major piece.

## Recently finished
- Public GitHub repo with v0.2.0 tagged; CI builds the wheel and attaches it to the release *(Sep 21)*
- Full live run on a real mailbox: OAuth, count, trash, undo, permanent delete all verified *(Sep 21)*
- Query builder with age, kind, and size controls; presets load into it via Customize *(Sep 21)*
- Streamed progress for count, trash, undo, delete; sizes in Gmail's units with Google-confirmed figures *(Sep 21)*
- Sweep runs as one local process installed from a wheel, no Node or Docker for end users *(Sep 21)*

## Still open
- [ ] Time a first-time user through SETUP.md — the Google Cloud walk-through is under 10 minutes or gets screenshots
- [ ] Senders view: real per-sender totals and a configurable sample — the table's counts mean what they look like they mean
- [ ] Claude "anything I should keep?" on the preview sample — flags exceptions in a query before trashing, off without a key
- [ ] MCP server exposing count, trash, senders, and empty trash — Claude Desktop can drive a cleanup with the same confirmation gates

## Pick up here
Start the MCP server over the existing count/trash/senders/untrash primitives, with the same confirmation gates.
