import { useState } from "react";
import { Download, LoaderCircle } from "lucide-react";
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

export default function DownloadPdfButton({
  versionId,
  projectName,
  periodKey,
  label = false,
  className = "",
  onError,
  beforeDownload,
}) {
  const [downloading, setDownloading] = useState(false);
  const toast = useToast();

  const download = async () => {
    if (downloading) return;
    setDownloading(true);
    try {
      if (beforeDownload) await beforeDownload();
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
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      toast.success("Report downloaded.", { title: "PDF ready" });
    } catch (e) {
      const msg = e.message || "Couldn't generate the PDF — try again.";
      onError?.(msg);
      toast.error(msg, { title: "Download failed" });
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
