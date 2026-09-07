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
  let res;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(getToken() ? { Authorization: `Bearer ${getToken()}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (cause) {
    // fetch() rejects only when the request never completed — the dev server is
    // down, the network dropped, or the request was blocked. Left unwrapped this
    // surfaced as "Failed to fetch", which every screen then rendered verbatim.
    const err = new Error("Couldn't reach the server. Check your connection and try again.");
    err.status = 0;
    err.cause = cause;
    throw err;
  }

  const data = await res.json().catch(() => ({}));

  if (res.status === 401) {
    onUnauthorised();
    const err = new Error(data.error || "Your session has expired — please sign in again.");
    err.status = 401;
    throw err;
  }

  if (!res.ok) {
    // Both keys are in use: FastAPI's own handlers raise `detail`, ours return
    // `error`. Reading only `error` meant a genuine server message was thrown
    // away in favour of the generic fallback.
    const fromServer = data.error || data.detail;

    // A 5xx with no JSON body at all is not an application error — it's the API
    // failing to answer. In dev that is nearly always Vite's proxy reporting
    // ECONNREFUSED because the FastAPI process isn't running, which arrives here
    // as a 500 with an empty text/plain body. Reporting that as "Something went
    // wrong." sends you looking for a bug in the app instead of starting the
    // backend.
    const upstreamSilent = res.status >= 500 && !fromServer;

    const err = new Error(
      fromServer ||
        (upstreamSilent
          ? `The server didn't respond (${res.status}). It may be restarting or not running.`
          : "Something went wrong.")
    );
    err.status = res.status;
    throw err;
  }
  return data;
}
