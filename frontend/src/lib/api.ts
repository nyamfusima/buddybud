const BASE = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "";
const TOKEN_KEY = "buddybud.token";

export const tokenStore = {
  get: () => { try { return sessionStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string) => { try { sessionStorage.setItem(TOKEN_KEY, t); } catch { /* storage blocked */ } },
  clear: () => { try { sessionStorage.removeItem(TOKEN_KEY); } catch { /* storage blocked */ } },
};

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

let onUnauthorized: () => void = () => {};
export function setUnauthorizedHandler(fn: () => void) { onUnauthorized = fn; }

function headers(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const t = tokenStore.get();
  if (t) h.Authorization = `Bearer ${t}`;
  return h;
}

async function handle<T>(res: Response): Promise<T> {
  if (res.status === 401) onUnauthorized();
  if (!res.ok) {
    let msg = `Request failed (${res.status})`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : Array.isArray(j.detail) ? j.detail.map((d: { msg: string }) => d.msg).join("; ") : msg;
    } catch { /* not json */ }
    throw new ApiError(res.status, msg);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => fetch(BASE + path, { headers: headers() }).then((r) => handle<T>(r)),
  del: <T>(path: string) => fetch(BASE + path, { method: "DELETE", headers: headers() }).then((r) => handle<T>(r)),
  post: <T>(path: string, body?: unknown) =>
    fetch(BASE + path, { method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body ?? {}) })
      .then((r) => handle<T>(r)),
  patch: <T>(path: string, body: unknown) =>
    fetch(BASE + path, { method: "PATCH", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify(body) })
      .then((r) => handle<T>(r)),
  upload: <T>(path: string, form: FormData) =>
    fetch(BASE + path, { method: "POST", headers: headers(), body: form }).then((r) => handle<T>(r)),
};

export type ChatEvent =
  | { type: "token"; data: string }
  | { type: "status"; data: string }
  | { type: "reset" }
  | { type: "done"; data: { text: string; safety: string | null } }
  | { type: "error"; data: string };

/** POST a message and stream the coach's Server-Sent Events back. */
export async function streamChat(message: string, onEvent: (e: ChatEvent) => void, signal?: AbortSignal): Promise<void> {
  const res = await fetch(BASE + "/api/coach/chat", {
    method: "POST", headers: headers({ "Content-Type": "application/json" }), body: JSON.stringify({ message }), signal,
  });
  if (!res.ok || !res.body) {
    await handle(res);
    return;
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx);
      buf = buf.slice(idx + 2);
      let ev = "message", data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) ev = line.slice(7);
        else if (line.startsWith("data: ")) data += line.slice(6);
      }
      const parsed = data ? JSON.parse(data) : null;
      if (ev === "reset") onEvent({ type: "reset" });
      else onEvent({ type: ev, data: parsed } as ChatEvent);
    }
  }
}
