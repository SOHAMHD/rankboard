import { useEffect, useMemo, useRef } from "react";
import { createPortal } from "react-dom";
import { Download, ExternalLink, LoaderCircle, RefreshCw, X } from "lucide-react";
import { BTN_GHOST, BTN_PRIMARY, monthLabel } from "../ui";
import { usePdfBlob } from "./usePdfBlob";

/**
 * Shows a generated report PDF in the app instead of making you download it,
 * open it, and delete it on every check.
 *
 * Deliberately not built on ui.jsx's `Modal`: that one is a small, padded
 * card (max-w-md) sized for forms, and a preview needs a near-fullscreen
 * chrome-less panel. Its Escape / scroll-lock / focus-restore behaviour is
 * reproduced here rather than widening the shared component, which every other
 * dialog in the app depends on.
 *
 * Rendering is the browser's own PDF viewer via an <iframe>, which brings
 * scroll, zoom, text search, page nav and print for free. The alternative —
 * pdf.js through react-pdf — is ~350 KB plus a worker to configure, and would
 * show a re-render of the document rather than the exact bytes the client
 * receives. For checking a report before it goes out, exactness is the point.
 */

// iOS Safari will not render a blob PDF in an iframe; it paints an empty grey
// box with no error. Detected once, so those users get a working action instead
// of a broken viewer.
const CAN_EMBED_PDF = (() => {
  if (typeof navigator === "undefined") return true;
  const isIOS =
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  return !isIOS;
})();

export default function PdfPreviewModal({
  open,
  onClose,
  versionId,
  periodKey,
  projectName,
  filename,
  cacheKey,
}) {
  const panelRef = useRef(null);

  const { status, objectUrl, filename: servedName, error, reload, download, openInNewTab } =
    usePdfBlob({ versionId, enabled: open, cacheKey, filename });

  // Native viewer flags: fit to width, sidebar collapsed. The toolbar is left on
  // — it carries print and page navigation, which we'd otherwise have to build.
  const src = useMemo(
    () => (objectUrl ? `${objectUrl}#view=FitH&navpanes=0` : null),
    [objectUrl]
  );

  useEffect(() => {
    if (!open) return undefined;

    const previouslyFocused = document.activeElement;
    panelRef.current?.focus();

    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    const onKeyDown = (e) => {
      if (e.key !== "Escape") return;
      // Capture-phase and stopped: this modal is opened from a menu that also
      // closes on Escape, and without this both would react to one keypress.
      e.stopPropagation();
      onClose?.();
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.body.style.overflow = prevOverflow;
      if (previouslyFocused instanceof HTMLElement) previouslyFocused.focus();
    };
  }, [open, onClose]);

  if (!open) return null;

  const heading = [projectName, periodKey && monthLabel(periodKey)].filter(Boolean).join(" · ");

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6">
      <div
        className="absolute inset-0"
        style={{ backgroundColor: "rgba(15, 23, 42, 0.55)" }}
        // mousedown rather than click, and only on the backdrop itself: a drag
        // that starts inside the PDF and releases out here shouldn't close it.
        onMouseDown={onClose}
      />

      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={heading ? `Report preview — ${heading}` : "Report preview"}
        className="relative flex w-full max-w-5xl h-[92vh] flex-col overflow-hidden rounded-2xl bg-white shadow-2xl focus:outline-none"
      >
        <div className="flex shrink-0 flex-wrap items-center justify-between gap-3 border-b border-stone-200 px-4 py-3">
          <div className="min-w-0">
            <h2 className="font-display text-base font-bold text-stone-900">
              Report preview{heading ? <span className="text-stone-400"> · {heading}</span> : null}
            </h2>
            <p className="truncate text-xs text-stone-400">
              #{versionId}
              {status === "ready" && servedName ? ` · ${servedName}` : ""}
            </p>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={reload}
              disabled={status === "loading"}
              title="Generate the PDF again from the server"
              className={`${BTN_GHOST} px-3 py-1.5`}
            >
              {status === "loading" ? (
                <LoaderCircle size={14} className="animate-spin" />
              ) : (
                <RefreshCw size={14} />
              )}
              Regenerate
            </button>
            <button
              onClick={openInNewTab}
              disabled={status !== "ready"}
              className={`${BTN_GHOST} px-3 py-1.5 disabled:opacity-40 disabled:cursor-not-allowed`}
            >
              <ExternalLink size={14} /> New tab
            </button>
            <button
              onClick={download}
              disabled={status !== "ready"}
              className={`${BTN_PRIMARY} px-3 py-1.5`}
            >
              <Download size={14} /> Download
            </button>
            <button
              onClick={onClose}
              aria-label="Close preview"
              className="rounded-md p-1.5 text-stone-500 transition-colors hover:bg-stone-100 hover:text-stone-700"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="relative min-h-0 flex-1 bg-stone-100">
          {status === "loading" && (
            <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
              <LoaderCircle size={26} className="animate-spin text-orange-600" />
              <p className="mt-1 text-sm font-semibold text-stone-900">Building the report…</p>
              <p className="max-w-sm text-xs text-stone-500">
                Chromium is rendering the PDF. This usually takes a few seconds.
              </p>
            </div>
          )}

          {status === "error" && (
            <div role="alert" className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
              <p className="text-sm font-semibold text-stone-900">Couldn't load the preview</p>
              <p className="max-w-md text-sm text-red-600">{error}</p>
              <button onClick={reload} className={`${BTN_PRIMARY} mt-2 px-4 py-2`}>
                <RefreshCw size={14} /> Try again
              </button>
            </div>
          )}

          {status === "ready" &&
            src &&
            (CAN_EMBED_PDF ? (
              <iframe src={src} title="Report preview" className="block h-full w-full border-0" />
            ) : (
              <div className="flex h-full flex-col items-center justify-center gap-2 p-8 text-center">
                <p className="text-sm font-semibold text-stone-900">
                  Inline preview isn't supported on this browser
                </p>
                <p className="max-w-sm text-xs text-stone-500">
                  Open the report in a new tab or download it instead.
                </p>
                <button onClick={openInNewTab} className={`${BTN_PRIMARY} mt-2 px-4 py-2`}>
                  <ExternalLink size={14} /> Open in new tab
                </button>
              </div>
            ))}
        </div>
      </div>
    </div>,
    document.body
  );
}
