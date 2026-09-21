# Plan

## The problem

15 GB Gmail quota, 14.7 GB used, ~60,000 messages. The web UI can only select 50 conversations at a time and each bulk action has several seconds of latency. Deleting everything before 2020 by hand would take hours.

## v1 — "done" means

- [ ] Sign in with Google, see storage used / total
- [ ] Run any preset: preview a count, trash in batches of 1,000 via `batchModify`
- [ ] Senders view: top 50 senders by count, trash-all per sender, unsubscribe link where present
- [ ] Claude suggestions per sender (keep / unsubscribe / trash + reason), applied only on confirmation
- [ ] Empty trash with a typed confirmation
- [ ] "Freed this session" counter
- [ ] README, architecture write-up, 2-minute demo video

Everything else is v2.

## Milestones

| # | Milestone | Proves |
|---|---|---|
| 1 | Scaffold, OAuth round-trip, storage gauge | Token flow works end to end |
| 2 | Presets via `batchModify` | The core speed claim — measure GB freed and minutes taken |
| 3 | Senders view + `List-Unsubscribe` | The thing Gmail's UI can't do |
| 4 | Claude suggestions | Turns a script into an assistant |
| 5 | Polish, docs, demo video | Portfolio deliverables |
| 6 | *(stretch)* Google OAuth verification | Open to the public |

## Go-live path

**Testing mode (v1 launch).** Google lets an unverified app run with up to 100 named test users. That's you, anyone you invite, and anyone who asks. Fully functional, no review.

**Verified (stretch).** `gmail.modify` is a restricted scope. Verification needs a hosted privacy policy and homepage, a demo video of the consent flow, brand verification (2–3 business days), and — because the backend handles Gmail data — a CASA Tier 2 assessment by a Google-approved lab, repeated annually. Budget a few hundred dollars and several weeks. Decide whether it's worth it after v1 has real users.

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
