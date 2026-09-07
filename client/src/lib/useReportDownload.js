import { useState } from "react";
import { BASE, getToken } from "../api";
import { useToast } from "../toast.jsx";
import { clearPdfCache } from "./usePdfBlob";

/**
 * Fetch-and-save for the two report formats.
 *
 * Lifted out of DownloadReportButton so the reports list can offer both formats
 * as plain buttons inside an expanded card, while the editor toolbars keep the
 * compact dropdown. Both call sites were otherwise going to hold their own copy
 * of the auth header, the filename rules and the save-before-download step.
 */

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "report";
}

export function reportFileName({ projectName, periodKey, versionId }) {
  if (projectName && periodKey) return `${slug(projectName)}-${slug(periodKey)}-seo-report.pdf`;
  if (projectName) return `${slug(projectName)}-seo-report.pdf`;
  return `report-${versionId}.pdf`;
}

// The Excel roll-up is named by the server, which knows the client name and the
// newest month in the sheet. Parsed rather than rebuilt here so the two can't drift.
function nameFromDisposition(header, fallback) {
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header || "");
  return match ? decodeURIComponent(match[1]) : fallback;
}

const saveToDisk = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

export function useReportDownload({ versionId, projectName, periodKey, beforeDownload, onError }) {
  // Per-format rather than one flag: with both buttons on screen at once, a
  // single `busy` would spin the Excel button while the PDF was building.
  const [busyKind, setBusyKind] = useState(null);
  const toast = useToast();

  const download = async (kind) => {
    if (busyKind) return;
    const excel = kind === "xlsx";
    const failure = excel
      ? "Couldn't build the Excel report — try again."
      : "Couldn't generate the PDF — try again.";

    setBusyKind(kind);
    try {
      // Runs for both formats. The Excel sheet reads the selected countries and
      // pages out of the saved document, so an unsaved draft would export the
      // previous selection.
      if (beforeDownload) {
        await beforeDownload();
        // The saved draft supersedes whatever the preview is holding.
        clearPdfCache(String(versionId));
      }
      const res = await fetch(`${BASE}/api/reports/${versionId}/${excel ? "xlsx" : "pdf"}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(
          body.error ||
            body.detail ||
            (res.status >= 500
              ? `The server didn't respond (${res.status}). It may be restarting or not running.`
              : failure)
        );
      }
      const blob = await res.blob();
      saveToDisk(
        blob,
        excel
          ? nameFromDisposition(res.headers.get("Content-Disposition"), "seo-report.xlsx")
          : reportFileName({ projectName, periodKey, versionId })
      );
      toast.success("Report downloaded.", { title: excel ? "Excel ready" : "PDF ready" });
    } catch (e) {
      const msg = e.message === "Failed to fetch" ? "Couldn't reach the server." : e.message || failure;
      onError?.(msg);
      toast.error(msg, { title: "Download failed" });
    } finally {
      setBusyKind(null);
    }
  };

  return { download, busyKind, busy: busyKind !== null };
}
