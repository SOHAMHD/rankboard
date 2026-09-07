import { useCallback, useEffect, useRef, useState } from "react";
import { BASE, getToken } from "../api";

/**
 * Fetches a report PDF as a Blob and hands back an object URL the browser's
 * native viewer can embed.
 *
 * The endpoint requires a Bearer token, so `<iframe src="/api/reports/1/pdf">`
 * can't be used directly — the same wall the download button hit with `<a href>`.
 * Fetching in JS, where the header can be set, and handing the viewer a blob URL
 * instead is what makes an in-app preview possible at all.
 */

// versionId (plus whatever else the caller folds into the key) -> { blob, filename }.
//
// Module-level rather than component state so closing and reopening the modal
// doesn't re-run the Playwright/Chromium print — that's several seconds of
// server work for a document we already have. Cleared on page reload, which is
// the right lifetime: a preview should never outlive the session that made it.
const cache = new Map();

export function clearPdfCache(key) {
  if (key === undefined) cache.clear();
  else cache.delete(key);
}

/** Mirrors nameFromDisposition in DownloadReportButton — the server names the
 *  file when it knows better than we do. */
function nameFromDisposition(header, fallback) {
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header || "");
  if (!match) return fallback;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

/**
 * @param {object}  opts
 * @param {number}  opts.versionId
 * @param {boolean} opts.enabled   Only fetches while true, i.e. the modal is open.
 * @param {string}  opts.cacheKey  Cache identity. Must change whenever the
 *                                 generated PDF would differ — see the caller.
 * @param {string}  opts.filename  Download name if the server doesn't supply one.
 */
export function usePdfBlob({ versionId, enabled, cacheKey, filename: fallbackName = "seo-report.pdf" }) {
  const [state, setState] = useState({
    status: "idle",
    objectUrl: null,
    blob: null,
    filename: fallbackName,
    error: null,
  });
  const objectUrlRef = useRef(null);
  const [nonce, setNonce] = useState(0);

  const key = cacheKey ?? String(versionId);

  const revoke = useCallback(() => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  const reload = useCallback(() => {
    clearPdfCache(key);
    setNonce((n) => n + 1);
  }, [key]);

  useEffect(() => {
    if (!enabled || !versionId) return undefined;

    let cancelled = false;

    const publish = ({ blob, filename }) => {
      if (cancelled) return;
      revoke();
      const objectUrl = URL.createObjectURL(blob);
      objectUrlRef.current = objectUrl;
      setState({ status: "ready", objectUrl, blob, filename, error: null });
    };

    const hit = cache.get(key);
    if (hit) {
      publish(hit);
      return () => {
        cancelled = true;
      };
    }

    setState((s) => ({ ...s, status: "loading", error: null }));

    const controller = new AbortController();

    (async () => {
      try {
        const res = await fetch(`${BASE}/api/reports/${versionId}/pdf`, {
          headers: { Authorization: `Bearer ${getToken()}` },
          signal: controller.signal,
        });

        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          const fromServer = body.error || body.detail;
          throw new Error(
            fromServer ||
              (res.status >= 500
                ? `The server didn't respond (${res.status}). It may be restarting or not running.`
                : "Couldn't generate the PDF — try again.")
          );
        }

        const raw = await res.blob();
        if (raw.size === 0) throw new Error("The server returned an empty PDF.");

        // Chromium embeds on the MIME type, not the extension. A proxy answering
        // application/octet-stream would make the iframe download the file
        // instead of showing it, so the type is asserted here.
        const blob =
          raw.type === "application/pdf" ? raw : new Blob([raw], { type: "application/pdf" });

        const entry = {
          blob,
          filename: nameFromDisposition(res.headers.get("Content-Disposition"), fallbackName),
        };
        cache.set(key, entry);
        publish(entry);
      } catch (e) {
        if (cancelled || e.name === "AbortError") return;
        setState({
          status: "error",
          objectUrl: null,
          blob: null,
          filename: fallbackName,
          // A network-level failure rejects with "Failed to fetch", which is not
          // something to put in front of a user.
          error: e.message === "Failed to fetch" ? "Couldn't reach the server." : e.message,
        });
      }
    })();

    return () => {
      cancelled = true;
      // Abandons an in-flight generation if the modal is closed while waiting.
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, versionId, key, nonce]);

  // A 5 MB blob leaked on every open adds up over an afternoon of report edits.
  useEffect(() => revoke, [revoke]);

  const download = useCallback(() => {
    if (!state.blob) return;
    const a = document.createElement("a");
    a.href = state.objectUrl;
    a.download = state.filename || fallbackName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    // Deliberately not revoked here: the modal is still displaying this URL.
    // The unmount effect above owns it.
  }, [state.blob, state.objectUrl, state.filename, fallbackName]);

  const openInNewTab = useCallback(() => {
    if (state.objectUrl) window.open(state.objectUrl, "_blank", "noopener");
  }, [state.objectUrl]);

  return { ...state, reload, download, openInNewTab };
}
