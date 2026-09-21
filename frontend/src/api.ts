const BASE = import.meta.env.VITE_API_BASE ?? "";

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
  me: () => req<{ email: string }>("/auth/me"),
  loginUrl: BASE + "/auth/login",
  logout: () => fetch(BASE + "/auth/logout", { method: "POST", credentials: "include" }),
  storage: () => req<Storage>("/api/storage"),
  presets: () => req<Preset[]>("/api/presets"),
  presetCount: (k: string) => req<{ estimate: number }>(`/api/presets/${k}/count`),
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
