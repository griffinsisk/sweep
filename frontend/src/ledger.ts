/** Per-account history in this browser's localStorage. The server stores
 * nothing, so this is the only memory Sweep has between visits. Every read
 * and write is guarded: private windows and blocked storage just mean no
 * history, never a broken page. */

export type Session = {
  at: string; // ISO start time
  usage: number; // Google's reported usage (bytes) when the session started
  estimatedFreed: number; // Sweep's sample-based estimate for permanent deletes
};
export type Ledger = { sessions: Session[] };

const key = (email: string) => `sweep:ledger:${email.toLowerCase()}`;

export function loadLedger(email: string): Ledger {
  try {
    const raw = localStorage.getItem(key(email));
    const parsed = raw ? (JSON.parse(raw) as Ledger) : null;
    return parsed && Array.isArray(parsed.sessions) ? parsed : { sessions: [] };
  } catch {
    return { sessions: [] };
  }
}

function save(email: string, ledger: Ledger) {
  try {
    localStorage.setItem(key(email), JSON.stringify(ledger));
  } catch {
    /* storage unavailable: history simply does not persist */
  }
}

const day = (iso: string) => iso.slice(0, 10);

/** Record this session's start. A session is one calendar day per account:
 * reloading the page or restarting the server on the same day continues the
 * existing record, so the count means "days you used Sweep", not page loads.
 * The first usage figure of the day is kept as that day's starting point. */
export function startSession(email: string, usage: number): Ledger {
  const ledger = loadLedger(email);
  const now = new Date().toISOString();
  const last = ledger.sessions[ledger.sessions.length - 1];
  if (!last || day(last.at) !== day(now)) {
    ledger.sessions.push({ at: now, usage, estimatedFreed: 0 });
    if (ledger.sessions.length > 50) ledger.sessions.splice(0, ledger.sessions.length - 50);
    save(email, ledger);
  }
  return ledger;
}

/** One-time repair for ledgers written before sessions were per day. */
export function collapseSameDay(email: string): Ledger {
  const ledger = loadLedger(email);
  const out: Session[] = [];
  for (const s of ledger.sessions) {
    const prev = out[out.length - 1];
    if (prev && day(prev.at) === day(s.at)) prev.estimatedFreed += s.estimatedFreed;
    else out.push({ ...s });
  }
  if (out.length !== ledger.sessions.length) save(email, { sessions: out });
  return { sessions: out };
}

/** Add to the current (last) session's estimate after a permanent delete. */
export function recordFreed(email: string, bytes: number): Ledger {
  const ledger = loadLedger(email);
  const cur = ledger.sessions[ledger.sessions.length - 1];
  if (cur) cur.estimatedFreed += bytes;
  save(email, ledger);
  return ledger;
}

/** What the history says, for the gauge's one-line summary. */
export function summarize(ledger: Ledger, currentUsage: number) {
  const first = ledger.sessions[0];
  if (!first) return null;
  return {
    firstAt: new Date(first.at),
    sessions: ledger.sessions.length,
    confirmedSinceFirst: Math.max(0, first.usage - currentUsage), // Google's ruler
    estimatedSinceFirst: ledger.sessions.reduce((n, s) => n + s.estimatedFreed, 0),
  };
}

/** Unsubscribe requests, by sender address, so a later scan can show that
 * a sender was already asked to stop. "Requested" is all we know: the
 * sender accepted the request, not that mail stopped. */
export type Unsubscribes = Record<string, string>; // address -> ISO date requested

const unsubKey = (email: string) => `sweep:unsub:${email.toLowerCase()}`;

export function loadUnsubscribes(email: string): Unsubscribes {
  try {
    const raw = localStorage.getItem(unsubKey(email));
    const parsed = raw ? (JSON.parse(raw) as Unsubscribes) : null;
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function recordUnsubscribe(email: string, address: string): Unsubscribes {
  const all = loadUnsubscribes(email);
  all[address.toLowerCase()] = new Date().toISOString();
  try {
    localStorage.setItem(unsubKey(email), JSON.stringify(all));
  } catch {
    /* storage unavailable: the row still shows "requested" until reload */
  }
  return all;
}
