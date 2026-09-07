import { useEffect, useRef, useState } from "react";
import { ChevronDown, Download, Eye, FileText, LoaderCircle, Table } from "lucide-react";
import { BTN_GHOST } from "../ui";
import { useToast } from "../toast.jsx";
import PdfPreviewModal from "./PdfPreviewModal";
import { clearPdfCache } from "./usePdfBlob";
import { reportFileName, useReportDownload } from "./useReportDownload";

/**
 * Compact preview + download pair for the editor toolbars.
 *
 * The reports list uses ReportVersionCard instead, which lays the same actions
 * out as labelled rows — a dropdown is the wrong shape when there's room to show
 * the choices. Both share useReportDownload so the fetch, filename and
 * save-first rules exist once.
 */
export default function DownloadReportButton({
  versionId,
  projectName,
  periodKey,
  label = false,
  className = "",
  onError,
  beforeDownload,
}) {
  const [open, setOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  // Separate from the download's busy flag so saving a draft ahead of a preview
  // doesn't spin the download control, and vice versa.
  const [previewBusy, setPreviewBusy] = useState(false);
  const wrapRef = useRef(null);
  const toast = useToast();

  const { download, busy } = useReportDownload({
    versionId,
    projectName,
    periodKey,
    beforeDownload,
    onError,
  });

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

  const pick = (kind) => {
    setOpen(false);
    download(kind);
  };

  const openPreview = async () => {
    if (busy || previewBusy) return;
    setOpen(false);
    if (beforeDownload) {
      setPreviewBusy(true);
      try {
        await beforeDownload();
        clearPdfCache(String(versionId));
      } catch (e) {
        // beforeDownload is the caller's save, which reports its own failure
        // through onError. Previewing an unsaved draft would show the wrong
        // document, so we stop rather than open something misleading.
        const msg = e?.message || "Couldn't save the draft — preview cancelled.";
        onError?.(msg);
        toast.error(msg, { title: "Preview failed" });
        return;
      } finally {
        setPreviewBusy(false);
      }
    }
    setPreviewOpen(true);
  };

  const menu = open && (
    <div
      role="menu"
      className="absolute right-0 top-full mt-1 z-30 w-56 rounded-lg border border-stone-200 bg-white shadow-lg py-1"
    >
      <button
        role="menuitem"
        onClick={() => pick("pdf")}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-orange-50 hover:text-orange-700 text-left"
      >
        <FileText size={14} /> Standard Report
      </button>
      <button
        role="menuitem"
        onClick={() => pick("xlsx")}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-stone-700 hover:bg-orange-50 hover:text-orange-700 text-left"
      >
        <Table size={14} /> Excel Report
      </button>
    </div>
  );

  const preview = (
    <PdfPreviewModal
      open={previewOpen}
      onClose={() => setPreviewOpen(false)}
      versionId={versionId}
      periodKey={periodKey}
      projectName={projectName}
      filename={reportFileName({ projectName, periodKey, versionId })}
      cacheKey={String(versionId)}
    />
  );

  if (label) {
    return (
      <div className="relative flex items-center gap-2" ref={wrapRef}>
        <button
          onClick={openPreview}
          disabled={busy || previewBusy}
          title="Open the report in the app"
          className={`${BTN_GHOST} px-3 py-1.5`}
        >
          {previewBusy ? <LoaderCircle size={14} className="animate-spin" /> : <Eye size={14} />} Preview
        </button>
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
        {preview}
      </div>
    );
  }

  return (
    <div className="relative flex items-center gap-0.5" ref={wrapRef}>
      <button
        onClick={openPreview}
        disabled={busy || previewBusy}
        aria-label={`Preview ${periodKey || `report ${versionId}`}`}
        title="Preview"
        className="inline-flex items-center justify-center rounded-lg p-1.5 text-stone-400 hover:text-orange-600 hover:bg-orange-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {previewBusy ? <LoaderCircle size={15} className="animate-spin" /> : <Eye size={15} />}
      </button>
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
      {preview}
    </div>
  );
}
