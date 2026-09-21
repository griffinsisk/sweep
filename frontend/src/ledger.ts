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

/** Record this session's start. Returns the ledger including the new session. */
export function startSession(email: string, usage: number): Ledger {
  const ledger = loadLedger(email);
  ledger.sessions.push({ at: new Date().toISOString(), usage, estimatedFreed: 0 });
  if (ledger.sessions.length > 50) ledger.sessions.splice(0, ledger.sessions.length - 50);
  save(email, ledger);
  return ledger;
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
