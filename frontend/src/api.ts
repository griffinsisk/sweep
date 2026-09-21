const BASE = "";

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
export type Count = {
  count: number;
  capped: boolean;
  done: boolean;
  avg_bytes?: number; // present on the final line: mean size of a 100-message sample
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
export type Sender = {
  address: string;
  domain: string;
  name: string;
  count: number;
  estimated_bytes: number;
  unsubscribe_url: string | null;
  subjects: string[];
};
export type Suggestion = { address: string; action: "keep" | "unsubscribe" | "trash"; reason: string };

export const api = {
  me: () => req<{ email: string; ai_enabled: boolean }>("/auth/me"),
  loginUrl: BASE + "/auth/login",
  logout: () => fetch(BASE + "/auth/logout", { method: "POST", credentials: "include" }),
  storage: () => req<Storage>("/api/storage"),
  presets: () => req<Preset[]>("/api/presets"),
  presetCount: (k: string) => ndjson<Count>(`/api/presets/${k}/count`),
  presetTrash: (k: string) => req<{ trashed: number }>(`/api/presets/${k}/trash`, { method: "POST" }),
  queryTrash: (query: string) =>
    req<{ trashed: number }>("/api/query/trash", { method: "POST", body: JSON.stringify({ query }) }),
  senders: (sample = 1000) => req<Sender[]>(`/api/senders?sample=${sample}`),
  suggest: (senders: Sender[]) =>
    req<Suggestion[]>("/api/ai/suggest", {
      method: "POST",
      body: JSON.stringify(
        senders.map((s) => ({ address: s.address, domain: s.domain, count: s.count, subjects: s.subjects }))
      ),
    }),
  emptyTrash: () =>
    req<{ deleted: number }>("/api/trash/empty", {
      method: "POST",
      body: JSON.stringify({ confirm: "DELETE FOREVER" }),
    }),
};

export const gb = (bytes?: number) => (bytes ? (bytes / 1e9).toFixed(1) : "0.0");
