/* ════════════════════════════════════════════════════════════════════
   API CLIENT — the frontend's single doorway to the backend.

   Every component calls api("/path") instead of fetch directly, so
   auth headers, JSON handling, and error shaping live in ONE place.

   The JWT is kept in localStorage so a page refresh doesn't log you
   out. Trade-off to know about: localStorage is readable by any JS
   on the page, so an XSS vulnerability could steal the token. The
   hardened alternative is an httpOnly cookie — a good later upgrade.
   ════════════════════════════════════════════════════════════════════ */
const TOKEN_KEY = "rankboard_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || "Something went wrong.");
  return data;
}
