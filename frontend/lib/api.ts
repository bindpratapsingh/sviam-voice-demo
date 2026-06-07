const BASE = (process.env.NEXT_PUBLIC_BACKEND_URL || "").replace(/\/$/, "");

async function post(path: string, body: any) {
  const r = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
}

export function createSession(language: string, strictness: string): Promise<{ session_id: string; room_url: string }> {
  return post("/sessions", { language, strictness });
}

export async function getScorecard(id: string) {
  const r = await fetch(`${BASE}/sessions/${id}/scorecard`);
  return r.json();
}

export function adminVerify(password: string) {
  return post("/admin/verify", { password });
}
export function adminSession(password: string, session_id: string) {
  return post("/admin/session", { password, session_id });
}
export function adminConfigGet(password: string) {
  return post("/admin/config/get", { password });
}
export function adminConfigSet(password: string, updates: any) {
  return post("/admin/config/set", { password, ...updates });
}
