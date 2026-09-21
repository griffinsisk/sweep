import { useEffect, useMemo, useState } from "react";
import { api, gb, Preset, Sender, Storage, Suggestion } from "./api";

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

function Dashboard({ email, aiEnabled }: { email: string; aiEnabled: boolean }) {
  const [storage, setStorage] = useState<Storage | null>(null);
  const [trashedThisSession, setTrashedThisSession] = useState(0);
  const [freedBytes, setFreedBytes] = useState(0);
  const [pendingBytes, setPendingBytes] = useState(0);

  const refreshStorage = () => api.storage().then(setStorage).catch(() => {});
  useEffect(() => {
    refreshStorage();
  }, []);

  const onTrashed = (count: number, estBytes = 0) => {
    setTrashedThisSession((n) => n + count);
    setPendingBytes((b) => b + estBytes);
  };
  const onEmptied = () => {
    setFreedBytes((f) => f + pendingBytes);
    setPendingBytes(0);
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

      <Presets onTrashed={onTrashed} />
      <Senders onTrashed={onTrashed} aiEnabled={aiEnabled} />
      <EmptyTrash trashedThisSession={trashedThisSession} onEmptied={onEmptied} />
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

function Presets({ onTrashed }: { onTrashed: (n: number) => void }) {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [status, setStatus] = useState<Record<string, Status>>({});
  const [counts, setCounts] = useState<Record<string, number>>({});

  useEffect(() => {
    api.presets().then(setPresets);
  }, []);

  const set = (k: string, s: Status) => setStatus((p) => ({ ...p, [k]: s }));

  const count = async (p: Preset) => {
    set(p.key, { kind: "counting" });
    try {
      const { estimate } = await api.presetCount(p.key);
      setCounts((c) => ({ ...c, [p.key]: estimate }));
      set(p.key, { kind: "idle" });
    } catch (e) {
      set(p.key, { kind: "err", text: String(e) });
    }
  };

  const trash = async (p: Preset) => {
    if (!confirm(`Move every message matching "${p.query}" to Trash?`)) return;
    set(p.key, { kind: "working", text: "Trashing in batches of 1,000…" });
    try {
      const { trashed } = await api.presetTrash(p.key);
      onTrashed(trashed);
      setCounts((c) => ({ ...c, [p.key]: 0 }));
      set(p.key, { kind: "ok", text: `Moved ${trashed.toLocaleString()} messages to Trash.` });
    } catch (e) {
      set(p.key, { kind: "err", text: String(e) });
    }
  };

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
                  {p.hint} <code>{p.query}</code>
                </div>
              </div>
              <div className="count">
                {s.kind === "counting"
                  ? "counting…"
                  : counts[p.key] !== undefined
                  ? `~${counts[p.key].toLocaleString()}`
                  : ""}
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button className="btn" disabled={busy} onClick={() => count(p)}>
                  Count
                </button>
                <button className="btn danger" disabled={busy} onClick={() => trash(p)}>
                  Trash all
                </button>
              </div>
              {s.text && <div className={`status ${s.kind}`}>{s.text}</div>}
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Senders({
  onTrashed,
  aiEnabled,
}: {
  onTrashed: (n: number, bytes: number) => void;
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
      onTrashed(trashed, s.estimated_bytes * (trashed / Math.max(1, s.count)));
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
  onEmptied,
}: {
  trashedThisSession: number;
  onEmptied: () => void;
}) {
  const [typed, setTyped] = useState("");
  const [status, setStatus] = useState<Status>({ kind: "idle" });

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
      <div className="dangerzone">
        <p style={{ marginTop: 0 }}>
          Type <strong>DELETE FOREVER</strong> to permanently delete everything in Trash.
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
