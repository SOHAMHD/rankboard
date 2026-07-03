/* Reusable "Download PDF" control for a report version.

   GET /api/reports/{id}/pdf is auth-gated, so a plain <a href> can't carry the
   Bearer token, and api() (JSON-only) can't read the binary body. We fetch the
   bytes with the token, then trigger a browser download via a temporary object
   URL. Rendering runs Playwright server-side (a couple of seconds), so the
   button shows a spinner and disables itself so it can't fire twice. On failure
   it calls onError with the server's {error} message instead of downloading a
   broken file. */
import { useState } from "react";
import { Download, LoaderCircle } from "lucide-react";
import { BASE, getToken } from "../api";
import { BTN_GHOST } from "../ui";

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "report";
}

// {project}-{period}-seo-report.pdf when the project is known, else report-{id}.pdf.
function fileName({ projectName, periodKey, versionId }) {
  if (projectName && periodKey) return `${slug(projectName)}-${slug(periodKey)}-seo-report.pdf`;
  if (projectName) return `${slug(projectName)}-seo-report.pdf`;
  return `report-${versionId}.pdf`;
}

export default function DownloadPdfButton({
  versionId,
  projectName,
  periodKey,
  label = false, // true → "Download PDF" text (editor headers); false → icon-only (list rows)
  className = "",
  onError,
}) {
  const [downloading, setDownloading] = useState(false);

  const download = async () => {
    if (downloading) return; // guard the double-click
    setDownloading(true);
    try {
      const res = await fetch(`${BASE}/api/reports/${versionId}/pdf`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || body.detail || "Couldn't generate the PDF — try again.");
      }
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fileName({ projectName, periodKey, versionId });
      document.body.appendChild(a);
      a.click(); // download starts synchronously here…
      a.remove();
      URL.revokeObjectURL(url); // …so it's safe to revoke now
    } catch (e) {
      onError?.(e.message || "Couldn't generate the PDF — try again.");
    } finally {
      setDownloading(false);
    }
  };

  if (label) {
    return (
      <button onClick={download} disabled={downloading} className={`${BTN_GHOST} px-3 py-1.5 ${className}`}>
        {downloading ? <LoaderCircle size={14} className="animate-spin" /> : <Download size={14} />} Download PDF
      </button>
    );
  }
  return (
    <button
      onClick={download}
      disabled={downloading}
      aria-label={`Download ${periodKey || `report ${versionId}`} as PDF`}
      title="Download PDF"
      className={`inline-flex items-center justify-center rounded-lg p-1.5 text-stone-400 hover:text-orange-600 hover:bg-orange-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {downloading ? <LoaderCircle size={15} className="animate-spin" /> : <Download size={15} />}
    </button>
  );
}
