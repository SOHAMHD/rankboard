import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, FileText, LoaderCircle, Table } from "lucide-react";
import { BASE, getToken } from "../api";
import { BTN_GHOST } from "../ui";
import { useToast } from "../toast.jsx";

function slug(s) {
  return String(s).toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "report";
}

function fileName({ projectName, periodKey, versionId }) {
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

const SAVE_TO_DISK = (blob, name) => {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
};

export default function DownloadReportButton({
  versionId,
  projectName,
  periodKey,
  label = false,
  className = "",
  onError,
  beforeDownload,
}) {
  const [busy, setBusy] = useState(false);
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const toast = useToast();

  useEffect(() => {
    if (!open) return undefined;
    const onDocClick = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const download = async (kind) => {
    if (busy) return;
    setOpen(false);
    setBusy(true);
    const excel = kind === "xlsx";
    const failure = excel
      ? "Couldn't build the Excel report — try again."
      : "Couldn't generate the PDF — try again.";
    try {
      // Runs for both formats. The Excel sheet reads the selected countries and
      // pages out of the saved document, so an unsaved draft would export the
      // previous selection.
      if (beforeDownload) await beforeDownload();
      const url = `${BASE}/api/reports/${versionId}/${excel ? "xlsx" : "pdf"}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${getToken()}` } });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || body.detail || failure);
      }
      const blob = await res.blob();
      SAVE_TO_DISK(
        blob,
        excel
          ? nameFromDisposition(res.headers.get("Content-Disposition"), "seo-report.xlsx")
          : fileName({ projectName, periodKey, versionId })
      );
      toast.success("Report downloaded.", { title: excel ? "Excel ready" : "PDF ready" });
    } catch (e) {
      const msg = e.message || failure;
      onError?.(msg);
      toast.error(msg, { title: "Download failed" });
    } finally {
      setBusy(false);
    }
  };

  const menu = open && (
    <div
      role="menu"
      className="absolute right-0 top-full mt-1 z-30 w-56 rounded-lg border border-stone-200 bg-white shadow-lg py-1"
    >
      <button
        role="menuitem"
        onClick={() => download("pdf")}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-orange-50 hover:text-orange-700 text-left"
      >
        <FileText size={14} /> Standard Report
      </button>
      <button
        role="menuitem"
        onClick={() => download("xlsx")}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-orange-50 hover:text-orange-700 text-left"
      >
        <Table size={14} /> Excel Report
      </button>
    </div>
  );

  if (label) {
    return (
      <div className="relative" ref={wrapRef}>
        <button
          onClick={() => setOpen((v) => !v)}
          disabled={busy}
          aria-haspopup="menu"
          aria-expanded={open}
          className={`${BTN_GHOST} px-3 py-1.5 ${className}`}
        >
          {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Download size={14} />} Download
          <ChevronDown size={13} className="opacity-60" />
        </button>
        {menu}
      </div>
    );
  }

  return (
    <div className="relative" ref={wrapRef}>
      <button
        onClick={() => setOpen((v) => !v)}
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Download ${periodKey || `report ${versionId}`}`}
        title="Download"
        className={`inline-flex items-center justify-center rounded-lg p-1.5 text-stone-400 hover:text-orange-600 hover:bg-orange-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
      >
        {busy ? <LoaderCircle size={15} className="animate-spin" /> : <Download size={15} />}
      </button>
      {menu}
    </div>
  );
}
