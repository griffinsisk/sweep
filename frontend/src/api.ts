const BASE = "";
const JSON_H = { "Content-Type": "application/json" };

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(BASE + path, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (r.status === 401) throw new Error("unauthenticated");
  if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail ?? r.statusText);
  return r.json();
}

export type Preset = { key: string; label: string; query: string; hint: string };
export type Preview = {
  sampled: number;
  oldest: string | null;
  newest: string | null;
  senders: { address: string; name: string; sampled: number }[];
  subjects: string[];
};
export type Count = {
  count: number;
  capped: boolean;
  done: boolean;
  avg_bytes?: number; // final line only: mean size across a 100-message sample
  preview?: Preview | null; // final line only: who/when/what, from the same sample
  error?: string;
};
export type TrashProgress = {
  phase: "listing" | "trashing" | "done";
  found?: number; // listing: ids found so far
  trashed?: number; // trashing/done: moved so far
  total?: number;
  ids?: string[]; // done: every id moved, kept by the browser for undo
  done: boolean;
  error?: string;
};
export type BatchProgress = {
  restored?: number;
  deleted?: number;
  total?: number;
  done: boolean;
  error?: string;
};

/** Read an NDJSON response line by line. */
export async function* ndjson<T>(path: string, init?: RequestInit): AsyncGenerator<T> {
  const r = await fetch(BASE + path, { credentials: "include", ...init });
  if (r.status === 401) throw new Error("unauthenticated");
  if (!r.ok) throw new Error((await r.json().catch(() => ({})))?.detail ?? r.statusText);
  const reader = r.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i: number;
    while ((i = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) yield JSON.parse(line) as T;
    }
  }
  if (buf.trim()) yield JSON.parse(buf) as T;
}
export type Storage = {
  messagesTotal: number | null;
  quota: { limit?: number; usage?: number; usageInDrive?: number } | null;
};
export type UnsubMethod = "one_click" | "mailto" | "manual";
export type Unsubscribe = {
  method: UnsubMethod; // one_click: Sweep POSTs. mailto: Sweep sends one message, if opted in. manual: a link.
  url: string | null;
  mailto: string | null;
};
export type Sender = {
  address: string;
  domain: string;
  name: string;
  sampled: number; // messages from this sender inside the sample
  total: number; // messages from this sender inside the scan scope
  capped: boolean; // total stopped at 10,000
  estimated_bytes: number; // mean sampled size x total
  unsubscribe: Unsubscribe | null;
  subjects: string[];
};
export type UnsubItem = { address: string; method: "one_click" | "mailto"; url?: string | null; mailto?: string | null };
export type UnsubProgress = {
  address?: string;
  status?: "requested" | "failed";
  detail?: string;
  requested?: number;
  failed?: number;
  done: boolean;
  error?: string;
};
export type Suggestion = { address: string; action: "keep" | "unsubscribe" | "trash"; reason: string };

export const api = {
  me: () => req<{ email: string; ai_enabled: boolean }>("/auth/me"),
  loginUrl: BASE + "/auth/login",
  logout: () => fetch(BASE + "/auth/logout", { method: "POST", credentials: "include" }),
  storage: () => req<Storage>("/api/storage"),
  presets: () => req<Preset[]>("/api/presets"),
  presetCount: (k: string, signal?: AbortSignal) => ndjson<Count>(`/api/presets/${k}/count`, { signal }),
  presetTrash: (k: string) => ndjson<TrashProgress>(`/api/presets/${k}/trash`, { method: "POST" }),
  queryCount: (query: string, signal?: AbortSignal) =>
    ndjson<Count>("/api/query/count", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
      signal,
    }),
  queryTrash: (query: string) =>
    ndjson<TrashProgress>("/api/query/trash", { method: "POST", headers: JSON_H, body: JSON.stringify({ query }) }),
  untrash: (ids: string[]) =>
    ndjson<BatchProgress>("/api/untrash", { method: "POST", headers: JSON_H, body: JSON.stringify({ ids }) }),
  deleteIds: (ids: string[]) =>
    ndjson<BatchProgress>("/api/delete", {
      method: "POST",
      headers: JSON_H,
      body: JSON.stringify({ ids, confirm: "DELETE FOREVER" }),
    }),
  senders: (sample: number, query: string) =>
    req<Sender[]>(`/api/senders?sample=${sample}&query=${encodeURIComponent(query)}`),
  unsubscribe: (items: UnsubItem[], allowMailto: boolean) =>
    ndjson<UnsubProgress>("/api/senders/unsubscribe", {
      method: "POST",
      headers: JSON_H,
      body: JSON.stringify({ items, allow_mailto: allowMailto }),
    }),
  suggest: (senders: Sender[]) =>
    req<Suggestion[]>("/api/ai/suggest", {
      method: "POST",
      body: JSON.stringify(
        senders.map((s) => ({ address: s.address, domain: s.domain, count: s.total, subjects: s.subjects }))
      ),
    }),
  emptyTrash: () =>
    req<{ deleted: number }>("/api/trash/empty", {
      method: "POST",
      body: JSON.stringify({ confirm: "DELETE FOREVER" }),
    }),
};

// Gmail's storage page divides by 2^30 and still says "GB". Match it, so a
// number here is the number the user sees in Google.
export const GB = 1024 ** 3;
export const gb = (bytes?: number, digits = 1) => (bytes ? (bytes / GB).toFixed(digits) : (0).toFixed(digits));
export const mb = (bytes?: number) => (bytes ? (bytes / 1024 ** 2).toFixed(1) : "0.0");
