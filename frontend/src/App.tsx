import { forwardRef, useEffect, useMemo, useRef, useState } from "react";
import { api, gb, Count, Preset, Preview, Sender, Storage, Suggestion, TrashResult } from "./api";

type Status = { kind: "idle" | "counting" | "working" | "ok" | "err"; text?: string };

export default function App() {
  const [email, setEmail] = useState<string | null>(null);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [authChecked, setAuthChecked] = useState(false);

  useEffect(() => {
    api
      .me()
      .then((m) => {
        setEmail(m.email);
        setAiEnabled(m.ai_enabled);
      })
      .catch(() => setEmail(null))
      .finally(() => setAuthChecked(true));
  }, []);

  if (!authChecked) return null;
  if (!email) return <SignIn />;
  return <Dashboard email={email} aiEnabled={aiEnabled} />;
}

function SignIn() {
  return (
    <main className="page signin">
      <h1>Sweep</h1>
      <p>
        Clear out years of Gmail in minutes. Trash everything before a date, see who
        actually fills your inbox, and let Claude suggest what to keep.
      </p>
      <a className="btn primary" href={api.loginUrl}>
        Sign in with Google
      </a>
      <p className="fine">
        Sweep runs on your own computer. Your Google token lives in your browser and is
        gone when you sign out. <a href="/PRIVACY.md">How your data is handled</a>
      </p>
    </main>
  );
}

type TrashEntry = { id: number; label: string; query: string; count: number; bytes: number; ids: string[] };
type Trashed = { trashed: number; bytes: number; ids: string[]; label: string; query: string };

function Dashboard({ email, aiEnabled }: { email: string; aiEnabled: boolean }) {
  const [storage, setStorage] = useState<Storage | null>(null);
  const [trashedThisSession, setTrashedThisSession] = useState(0);
  const [freedBytes, setFreedBytes] = useState(0);
  const [pendingBytes, setPendingBytes] = useState(0);
  const [log, setLog] = useState<TrashEntry[]>([]);
  const [seed, setSeed] = useState<{ query: string; n: number }>({ query: "", n: 0 });
  const builderRef = useRef<HTMLElement>(null);
  const customize = (query: string) => {
    setSeed((s) => ({ query, n: s.n + 1 }));
    builderRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const refreshStorage = () => api.storage().then(setStorage).catch(() => {});
  useEffect(() => {
    refreshStorage();
  }, []);

  const onTrashed = (t: Trashed) => {
    setTrashedThisSession((n) => n + t.trashed);
    setPendingBytes((b) => b + t.bytes);
    setLog((l) => [
      ...l,
      { id: Date.now(), label: t.label, query: t.query, count: t.trashed, bytes: t.bytes, ids: t.ids },
    ]);
  };
  const onRestored = (entry: TrashEntry, restored: number) => {
    setTrashedThisSession((n) => n - restored);
    setPendingBytes((b) => Math.max(0, b - entry.bytes));
    setLog((l) => l.filter((e) => e.id !== entry.id));
  };
  const onEmptied = () => {
    setFreedBytes((f) => f + pendingBytes);
    setPendingBytes(0);
    setLog([]);
    refreshStorage();
  };

  return (
    <main className="page">
      <header className="masthead">
        <h1>Sweep</h1>
        <span className="who">
          {email} ·{" "}
          <button className="linkish" onClick={() => api.logout().then(() => location.reload())}>
            Sign out
          </button>
        </span>
      </header>

      <Gauge storage={storage} pendingBytes={pendingBytes} freedBytes={freedBytes} />

      <Presets onTrashed={onTrashed} onCustomize={customize} />
      <QueryBuilder ref={builderRef} seed={seed} onTrashed={onTrashed} />
      <Senders
        aiEnabled={aiEnabled}
        onTrashed={(n, bytes, sender) => onTrashed({ trashed: n, bytes, ids: [], label: sender, query: "" })}
      />
      <EmptyTrash
        trashedThisSession={trashedThisSession}
        log={log}
        onRestored={onRestored}
        onEmptied={onEmptied}
      />
    </main>
  );
}

function Gauge({
  storage,
  pendingBytes,
  freedBytes,
}: {
  storage: Storage | null;
  pendingBytes: number;
  freedBytes: number;
}) {
  const limit = storage?.quota?.limit ?? 15e9;
  const usage = storage?.quota?.usage ?? 0;
  const usedPct = Math.min(100, (Math.max(0, usage - pendingBytes) / limit) * 100);
  const pendingPct = Math.min(100 - usedPct, (pendingBytes / limit) * 100);

  return (
    <section className="gauge" aria-label="Storage">
      <p className="headline">
        {gb(usage)}
        <small>of {gb(limit)} GB used</small>
      </p>
      <p className="sub">
        {storage?.messagesTotal ? `${storage.messagesTotal.toLocaleString()} messages. ` : ""}
        {pendingBytes > 0
          ? `About ${gb(pendingBytes)} GB is in Trash — empty it below to get that space back.`
          : "Trashing doesn't free space until you empty the trash."}
      </p>
      <div className="bar" role="img" aria-label={`${usedPct.toFixed(0)}% used`}>
        <div className="used" style={{ width: `${usedPct}%` }} />
        <div className="pending" style={{ width: `${pendingPct}%` }} />
      </div>
      <div className="legend">
        <span className="l-used">Used</span>
        <span className="l-pending">In trash</span>
        {freedBytes > 0 && <span className="l-freed">Freed this session: {gb(freedBytes)} GB</span>}
      </div>
    </section>
  );
}

/** Count + trash state for any set of Gmail queries, keyed by string. */
function useQueryActions(onTrashed: (t: Trashed) => void) {
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [counts, setCounts] = useState<Record<string, Count>>({});
  const set = (k: string, s: Status) => setStatus((p) => ({ ...p, [k]: s }));

  const count = async (key: string, stream: AsyncGenerator<Count>) => {
    set(key, { kind: "counting" });
    try {
      let last: Count | undefined;
      for await (const line of stream) {
        if (line.error) throw new Error(line.error);
        if (typeof line.count !== "number") throw new Error("Unexpected response. Restart sweep.");
        last = line;
        setCounts((c) => ({ ...c, [key]: line }));
      }
      if (last && !last.done) {
        // Stream ended without a final line: keep the count, skip the size estimate.
        setCounts((c) => ({ ...c, [key]: { ...last!, done: true } }));
        set(key, { kind: "err", text: "Count finished early; size estimate unavailable." });
        return;
      }
      set(key, { kind: "idle" });
    } catch (e) {
      set(key, { kind: "err", text: String(e) });
    }
  };

  const trash = async (
    key: string,
    label: string,
    query: string,
    run: () => Promise<TrashResult>,
    after?: () => void
  ) => {
    if (!confirm(`Move every message matching "${query}" to Trash?`)) return;
    set(key, { kind: "working", text: "Trashing in batches of 1,000…" });
    try {
      const { trashed, ids } = await run();
      const bytes = trashed * (counts[key]?.avg_bytes ?? 0);
      onTrashed({ trashed, bytes, ids, label, query });
      setCounts(({ [key]: _, ...rest }) => rest);
      set(key, {
        kind: "ok",
        text: `Moved ${trashed.toLocaleString()} messages to Trash. Undo is in the Empty trash section below.`,
      });
      after?.();
    } catch (e) {
      set(key, { kind: "err", text: String(e) });
    }
  };

  return { status, counts, count, trash };
}

/** What a query holds, from the 100-message sample Count already fetched. */
function PreviewPanel({ p, total }: { p: Preview; total: number }) {
  const [open, setOpen] = useState(false);
  const share = (n: number) => `${Math.max(1, Math.round((n / p.sampled) * 100))}%`;
  return (
    <div className="preview">
      <button className="linkish" onClick={() => setOpen((o) => !o)}>
        {open ? "Hide preview" : "Preview what's in here"}
      </button>
      {open && (
        <div className="preview-body">
          <p>
            Based on {p.sampled} messages sampled evenly across {total.toLocaleString()} matches
            {p.oldest && p.newest && (
              <>
                , dated <strong>{p.oldest}</strong> to <strong>{p.newest}</strong>
              </>
            )}
            .
          </p>
          <div className="preview-cols">
            <div>
              <div className="k">Who sent them</div>
              <ul>
                {p.senders.map((x) => (
                  <li key={x.address}>
                    <span className="name">{x.name || x.address}</span>
                    {x.name && <span className="addr"> {x.address}</span>}
                    <span className="share">~{share(x.sampled)}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <div className="k">A few subjects</div>
              <ul>
                {p.subjects.map((t, i) => (
                  <li key={i}>{t}</li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Presets({
  onTrashed,
  onCustomize,
}: {
  onTrashed: (t: Trashed) => void;
  onCustomize: (query: string) => void;
}) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const { status, counts, count, trash } = useQueryActions(onTrashed);

  useEffect(() => {
    api.presets().then(setPresets);
  }, []);

  return (
    <section>
      <h2>Presets</h2>
      <p className="lede">
        Each preset is an ordinary Gmail search — paste it into Gmail to check exactly what
        it matches before you run it.
      </p>
      <div className="rows">
        {presets.map((p) => {
          const s = status[p.key] ?? { kind: "idle" };
          const busy = s.kind === "working" || s.kind === "counting";
          return (
            <div className="row" key={p.key}>
              <div>
                <div className="label">{p.label}</div>
                <div className="hint">
                  {p.hint} <code>{p.query}</code>{" "}
                  <button className="linkish" onClick={() => onCustomize(p.query)}>
                    Customize
                  </button>
                </div>
              </div>
              <div className="count">
                <CountCell c={counts[p.key]} counting={s.kind === "counting"} />
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn" disabled={busy} onClick={() => count(p.key, api.presetCount(p.key))}>
                  Count
                </button>
                <button
                  className="btn danger"
                  disabled={busy}
                  onClick={() => trash(p.key, p.label, p.query, () => api.presetTrash(p.key))}
                >
                  Trash all
                </button>
              </div>
              {s.text && <div className={`status ${s.kind}`}>{s.text}</div>}
              {counts[p.key]?.preview && counts[p.key].count > 0 && (
                <PreviewPanel p={counts[p.key].preview!} total={counts[p.key].count} />
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}

/* ---- Query builder ------------------------------------------------------ */

const AGES: { label: string; value: string }[] = [
  { label: "Any age", value: "" },
  { label: "Older than 3 months", value: "older_than:3m" },
  { label: "Older than 6 months", value: "older_than:6m" },
  { label: "Older than 1 year", value: "older_than:1y" },
  { label: "Older than 2 years", value: "older_than:2y" },
  { label: "Older than 3 years", value: "older_than:3y" },
  { label: "Older than 5 years", value: "older_than:5y" },
  { label: "Before a date…", value: "before" },
];
const CATEGORIES = ["promotions", "social", "updates", "forums"] as const;
const SIZES: { label: string; value: string }[] = [
  { label: "Any size", value: "" },
  { label: "Larger than 1 MB", value: "larger:1M" },
  { label: "Larger than 5 MB", value: "larger:5M" },
  { label: "Larger than 10 MB", value: "larger:10M" },
  { label: "Larger than 25 MB", value: "larger:25M" },
];
const NOREPLY = "(from:noreply OR from:no-reply OR from:donotreply)";

type Controls = {
  age: string; // one of AGES[].value
  before: string; // YYYY-MM-DD when age === "before"
  cats: string[];
  attachment: boolean;
  noreply: boolean;
  size: string;
};
const EMPTY: Controls = { age: "", before: "", cats: [], attachment: false, noreply: false, size: "" };

function buildQuery(c: Controls): string {
  const parts: string[] = [];
  if (c.cats.length === 1) parts.push(`category:${c.cats[0]}`);
  if (c.cats.length > 1) parts.push(`(${c.cats.map((x) => `category:${x}`).join(" OR ")})`);
  if (c.attachment) parts.push("has:attachment");
  if (c.noreply) parts.push(NOREPLY);
  if (c.size) parts.push(c.size);
  if (c.age === "before" && c.before) parts.push(`before:${c.before.replace(/-/g, "/")}`);
  else if (c.age && c.age !== "before") parts.push(c.age);
  return parts.join(" ");
}

/** Best-effort inverse of buildQuery so "Customize" lights up the right controls. */
function parseQuery(q: string): Controls {
  const c: Controls = { ...EMPTY, cats: [] };
  const age = q.match(/older_than:\d+[dmy]/)?.[0];
  if (age && AGES.some((a) => a.value === age)) c.age = age;
  const before = q.match(/before:(\d{4})\/(\d{2})\/(\d{2})/);
  if (before) (c.age = "before"), (c.before = `${before[1]}-${before[2]}-${before[3]}`);
  for (const cat of CATEGORIES) if (q.includes(`category:${cat}`)) c.cats.push(cat);
  c.attachment = q.includes("has:attachment");
  c.noreply = q.includes(NOREPLY);
  const size = q.match(/larger:\d+M/)?.[0];
  if (size && SIZES.some((s) => s.value === size)) c.size = size;
  return c;
}

const QueryBuilder = forwardRef<
  HTMLElement,
  { seed: { query: string; n: number }; onTrashed: (t: Trashed) => void }
>(function QueryBuilder({ seed, onTrashed }, ref) {
  const [controls, setControls] = useState<Controls>(EMPTY);
  const [query, setQuery] = useState("");
  const { status, counts, count, trash } = useQueryActions(onTrashed);
  const reset = () => {
    setControls(EMPTY);
    setQuery("");
  };

  // A preset's "Customize" loads its query and lights up matching controls.
  useEffect(() => {
    if (!seed.n) return;
    setQuery(seed.query);
    setControls(parseQuery(seed.query));
  }, [seed]);

  const update = (patch: Partial<Controls>) => {
    const next = { ...controls, ...patch };
    setControls(next);
    setQuery(buildQuery(next));
  };
  const toggleCat = (cat: string) =>
    update({ cats: controls.cats.includes(cat) ? controls.cats.filter((x) => x !== cat) : [...controls.cats, cat] });

  const key = "builder";
  const s = status[key] ?? { kind: "idle" };
  const busy = s.kind === "working" || s.kind === "counting";
  const ready = query.trim().length > 0;

  return (
    <section ref={ref}>
      <h2>Build your own</h2>
      <p className="lede">
        Pick an age, a kind of mail, and a size. Sweep writes the Gmail search for you; edit
        it if you know the syntax. Count first, then trash.
      </p>
      <div className="builder">
        <label>
          <span>Age</span>
          <select value={controls.age} onChange={(e) => update({ age: e.target.value })}>
            {AGES.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
          {controls.age === "before" && (
            <input
              type="date"
              value={controls.before}
              onChange={(e) => update({ before: e.target.value })}
              aria-label="Before date"
            />
          )}
        </label>
        <fieldset>
          <legend>Kind of mail</legend>
          {CATEGORIES.map((cat) => (
            <label key={cat} className="check">
              <input type="checkbox" checked={controls.cats.includes(cat)} onChange={() => toggleCat(cat)} />
              {cat[0].toUpperCase() + cat.slice(1)}
            </label>
          ))}
          <label className="check">
            <input
              type="checkbox"
              checked={controls.attachment}
              onChange={(e) => update({ attachment: e.target.checked })}
            />
            Has attachment
          </label>
          <label className="check">
            <input type="checkbox" checked={controls.noreply} onChange={(e) => update({ noreply: e.target.checked })} />
            No-reply senders
          </label>
        </fieldset>
        <label>
          <span>Size</span>
          <select value={controls.size} onChange={(e) => update({ size: e.target.value })}>
            {SIZES.map((z) => (
              <option key={z.value} value={z.value}>
                {z.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="rows">
        <div className="row">
          <div>
            <div className="label">Your query</div>
            <input
              className="query"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. category:social older_than:3y"
              spellCheck={false}
              aria-label="Gmail search query"
            />
            <div className="hint">Same syntax as Gmail's search bar. Paste it there to preview matches.</div>
          </div>
          <div className="count">
            <CountCell c={counts[key]} counting={s.kind === "counting"} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button className="btn" disabled={busy || !ready} onClick={() => count(key, api.queryCount(query))}>
              Count
            </button>
            <button
              className="btn danger"
              disabled={busy || !ready}
              onClick={() => trash(key, `Custom: ${query}`, query, () => api.queryTrash(query), reset)}
            >
              Trash all
            </button>
          </div>
          {s.text && <div className={`status ${s.kind}`}>{s.text}</div>}
          {counts[key]?.preview && counts[key].count > 0 && (
            <PreviewPanel p={counts[key].preview!} total={counts[key].count} />
          )}
        </div>
      </div>
    </section>
  );
});

function CountCell({ c, counting }: { c?: Count; counting: boolean }) {
  if (!c) return counting ? <>counting…</> : null;
  const n = `${c.count.toLocaleString()}${c.capped ? "+" : ""}`;
  if (counting || !c.done) return <>{n}…</>;
  const bytes = c.count * (c.avg_bytes ?? 0);
  return (
    <>
      {n}
      {bytes > 0 && (
        <div className="size">
          ≈ {gb(bytes)} GB{c.capped ? "+" : ""}
        </div>
      )}
    </>
  );
}

function Senders({
  onTrashed,
  aiEnabled,
}: {
  onTrashed: (n: number, bytes: number, sender: string) => void;
  aiEnabled: boolean;
}) {
  const [senders, setSenders] = useState<Sender[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestions, setSuggestions] = useState<Record<string, Suggestion>>({});
  const [rowStatus, setRowStatus] = useState<Record<string, string>>({});

  const load = async () => {
    setLoading(true);
    try {
      setSenders(await api.senders(1000));
    } finally {
      setLoading(false);
    }
  };

  const suggest = async () => {
    if (!senders) return;
    setSuggesting(true);
    try {
      const out = await api.suggest(senders);
      setSuggestions(Object.fromEntries(out.map((s) => [s.address, s])));
    } catch (e) {
      alert(String(e));
    } finally {
      setSuggesting(false);
    }
  };

  const trashSender = async (s: Sender) => {
    if (!confirm(`Trash every message from ${s.address}?`)) return;
    setRowStatus((r) => ({ ...r, [s.address]: "trashing…" }));
    try {
      const { trashed } = await api.queryTrash(`from:${s.address}`);
      onTrashed(trashed, s.estimated_bytes * (trashed / Math.max(1, s.count)), `From ${s.address}`);
      setRowStatus((r) => ({ ...r, [s.address]: `trashed ${trashed}` }));
    } catch (e) {
      setRowStatus((r) => ({ ...r, [s.address]: String(e) }));
    }
  };

  const totalSampled = useMemo(() => senders?.reduce((n, s) => n + s.count, 0) ?? 0, [senders]);

  return (
    <section>
      <h2>Who fills your inbox</h2>
      <p className="lede">
        A sample of your older mail grouped by sender. Trash a sender in one click, or
        unsubscribe where they've given us a link.
      </p>
      <div className="toolbar">
        <button className="btn" onClick={load} disabled={loading}>
          {loading ? "Scanning 1,000 messages…" : senders ? "Rescan" : "Scan my inbox"}
        </button>
        {senders && aiEnabled && (
          <button className="btn" onClick={suggest} disabled={suggesting}>
            {suggesting ? "Asking Claude…" : "Ask Claude what to do"}
          </button>
        )}
        {senders && !aiEnabled && (
          <span className="hint" style={{ color: "var(--muted)", fontSize: 13 }}>
            Claude suggestions are off. Set ANTHROPIC_API_KEY to enable them.
          </span>
        )}
        {senders && (
          <span className="hint" style={{ color: "var(--muted)", fontSize: 13 }}>
            {senders.length} senders across {totalSampled.toLocaleString()} messages
          </span>
        )}
      </div>

      {senders && (
        <table>
          <thead>
            <tr>
              <th>Sender</th>
              <th className="num">Messages</th>
              <th className="num">Size</th>
              <th>Suggestion</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {senders.map((s) => {
              const sug = suggestions[s.address];
              return (
                <tr key={s.address}>
                  <td>
                    <div className="name">{s.name || s.domain}</div>
                    <div className="addr">{s.address}</div>
                  </td>
                  <td className="num">{s.count}</td>
                  <td className="num">{(s.estimated_bytes / 1e6).toFixed(1)} MB</td>
                  <td>
                    {sug && (
                      <>
                        <span className={`tag ${sug.action}`}>{sug.action}</span>
                        <div className="reason">{sug.reason}</div>
                      </>
                    )}
                  </td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    {s.unsubscribe_url && (
                      <a className="btn" href={s.unsubscribe_url} target="_blank" rel="noreferrer">
                        Unsubscribe
                      </a>
                    )}{" "}
                    <button className="btn danger" onClick={() => trashSender(s)}>
                      Trash all
                    </button>
                    {rowStatus[s.address] && (
                      <div className="reason">{rowStatus[s.address]}</div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </section>
  );
}

function EmptyTrash({
  trashedThisSession,
  log,
  onRestored,
  onEmptied,
}: {
  trashedThisSession: number;
  log: TrashEntry[];
  onRestored: (entry: TrashEntry, restored: number) => void;
  onEmptied: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });
  const [undoing, setUndoing] = useState<Record<number, string>>({});

  const undo = async (e: TrashEntry) => {
    setUndoing((u) => ({ ...u, [e.id]: "restoring…" }));
    try {
      const { restored } = await api.untrash(e.ids);
      onRestored(e, restored);
    } catch (err) {
      setUndoing((u) => ({ ...u, [e.id]: String(err) }));
    }
  };

  const run = async () => {
    setStatus({ kind: "working", text: "Deleting permanently…" });
    try {
      const { deleted } = await api.emptyTrash();
      setStatus({ kind: "ok", text: `Permanently deleted ${deleted.toLocaleString()} messages.` });
      setTyped("");
      onEmptied();
    } catch (e) {
      setStatus({ kind: "err", text: String(e) });
    }
  };

  return (
    <section>
      <h2>Empty trash</h2>
      <p className="lede">
        This is the step that actually gives you storage back — and the one you can't undo.
        {trashedThisSession > 0 &&
          ` You've moved ${trashedThisSession.toLocaleString()} messages to Trash this session.`}
      </p>

      {log.length > 0 && (
        <div className="rows" style={{ marginBottom: 16 }}>
          {log.map((e) => (
            <div className="row" key={e.id}>
              <div>
                <div className="label">{e.label}</div>
                {e.query && (
                  <div className="hint">
                    <code>{e.query}</code>
                  </div>
                )}
              </div>
              <div className="count">
                {e.count.toLocaleString()}
                {e.bytes > 0 && <div className="size">≈ {gb(e.bytes)} GB</div>}
              </div>
              <div>
                {e.ids.length > 0 ? (
                  <button className="btn" disabled={undoing[e.id] === "restoring…"} onClick={() => undo(e)}>
                    Undo
                  </button>
                ) : (
                  <span className="hint">restore in Gmail</span>
                )}
              </div>
              {undoing[e.id] && undoing[e.id] !== "restoring…" && (
                <div className="status err">{undoing[e.id]}</div>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="dangerzone">
        <p style={{ marginTop: 0 }}>
          Type <strong>DELETE FOREVER</strong> to permanently delete everything in Trash.
          {log.length > 0 && " Undo above stops working once you do."}
        </p>
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder="DELETE FOREVER"
            aria-label="Confirmation"
          />
          <button
            className="btn danger"
            disabled={typed !== "DELETE FOREVER" || status.kind === "working"}
            onClick={run}
          >
            Empty trash now
          </button>
        </div>
        {status.text && (
          <p className={`status ${status.kind}`} style={{ marginBottom: 0, fontSize: 13 }}>
            {status.text}
          </p>
        )}
      </div>
    </section>
  );
}
