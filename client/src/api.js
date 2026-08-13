const TOKEN_KEY = "rankboard_token";

export const BASE = import.meta.env.VITE_API_BASE_URL || "";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) =>
  t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY);

/**
 * Fired once when the server rejects our token. App.jsx listens and clears the
 * session; anything else that cares can too.
 */
export const SESSION_EXPIRED = "rankboard:session-expired";

// Tokens last 8 hours, so expiry mid-session is routine rather than exceptional.
// Nothing used to handle it: the app stayed "signed in" and every screen
// degraded into whatever its failure state looked like — a permanent spinner on
// Traffic, "No projects yet" on the projects list, "No emails match these
// filters" on the log. The user had to work out for themselves that signing out
// and back in fixed it. One guard here covers every screen.
let notified = false;

function onUnauthorised() {
  // Guarded: a screen firing six parallel requests would otherwise dispatch six
  // events and stack six toasts for one expiry.
  if (notified) return;
  notified = true;
  setToken(null);
  window.dispatchEvent(new CustomEvent(SESSION_EXPIRED));
  // Released once the app has had a chance to react, so a genuine second expiry
  // later in the session is still reported.
  setTimeout(() => { notified = false; }, 5000);
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(`${BASE}/api${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const data = await res.json().catch(() => ({}));

  if (res.status === 401) {
    onUnauthorised();
    const err = new Error(data.error || "Your session has expired — please sign in again.");
    err.status = 401;
    throw err;
  }

  if (!res.ok) {
    const err = new Error(data.error || "Something went wrong.");
    err.status = res.status;
    throw err;
  }
  return data;
}
