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
The app now runs as a single Python process that serves its own compiled UI on 127.0.0.1 and opens the browser. Google OAuth uses a Desktop app client with a loopback redirect, so the only external setup is the user's own Google Cloud project. Claude suggestions are optional and the UI says so when no key is set. The wheel builds with the UI inside it and CI is set to attach it to a GitHub Release on tags. Nothing has been run against a real mailbox since the restructure, and the repo has no GitHub remote yet.

## Recently finished
- Sweep runs as one local process installed from a wheel, no Node or Docker for end users *(Sep 21)*
- Repo extracted from the home directory into its own git history *(Sep 21)*

## Still open
- [ ] Real-mailbox run through sign-in, trash, and empty trash on the single-process build — proves the restructure did not break OAuth
- [ ] Push to GitHub and tag v0.2.0 — the install URLs in README and SETUP resolve
- [ ] Time a first-time user through SETUP.md — the Google Cloud walk-through is under 10 minutes or gets screenshots
- [ ] MCP server exposing count, trash, senders, and empty trash — Claude Desktop can drive a cleanup with the same confirmation gates

## Pick up here
Run `sweep` against your own Gmail with a fresh Desktop app OAuth client and confirm the full flow works.
