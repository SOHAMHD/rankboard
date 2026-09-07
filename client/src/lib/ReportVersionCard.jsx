import { useId, useState } from "react";
import { ChevronDown, Eye, LoaderCircle, Table, FileText, Trash2 } from "lucide-react";
import { BTN_GHOST, BTN_PRIMARY, monthLabel } from "../ui";
import PdfPreviewModal from "./PdfPreviewModal";
import SendReportButton from "./SendReportButton";
import { reportFileName, useReportDownload } from "./useReportDownload";

/**
 * One report version. Collapsed it states what the report is; expanded it offers
 * what you can do with it.
 *
 * The row used to carry six controls at once — badge, preview, download menu,
 * send, open, delete — which left the two formats invisible behind an icon and
 * the row itself unreadable. Splitting it means the line you scan holds only
 * identity and state, and the actions get room to be named.
 */

const STATUS_BADGE = {
  draft: "bg-emerald-100 text-emerald-700",
  in_review: "bg-amber-100 text-amber-700",
  sent: "bg-stone-200 text-stone-600",
};

export default function ReportVersionCard({
  version,
  projectName,
  projectId,
  canSend,
  canDelete,
  onOpen,
  onDelete,
  onError,
}) {
  const [expanded, setExpanded] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const panelId = useId();

  const { download, busyKind } = useReportDownload({
    versionId: version.id,
    projectName,
    periodKey: version.periodKey,
    onError,
  });

  return (
    <div className="bg-white border border-stone-200 rounded-xl">
      <div className="flex items-center gap-2 px-3 py-2.5 sm:px-4">
        {/* The expand control is the row. Open/Edit sits beside it rather than
            inside — a button within a button is invalid, and assistive tech
            announces the pair as one confused control. */}
        <button
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          aria-controls={panelId}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg py-0.5 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500"
        >
          <span className="min-w-0">
            <span className="flex items-center gap-2">
              <span className="text-sm font-medium text-stone-900">
                {monthLabel(version.periodKey)}
              </span>
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                  STATUS_BADGE[version.status] || "bg-stone-200 text-stone-600"
                }`}
              >
                {version.status}
              </span>
            </span>
            <span className="block truncate text-xs text-stone-400">
              #{version.id} · {version.createdAt}
              {version.parentVersionId ? ` · forked from #${version.parentVersionId}` : ""}
            </span>
          </span>
          <ChevronDown
            size={16}
            className={`ml-auto shrink-0 text-stone-400 transition-transform ${
              expanded ? "rotate-180" : ""
            }`}
          />
        </button>

        <button onClick={onOpen} className={`${BTN_PRIMARY} shrink-0 px-3 py-1.5`}>
          {version.status === "draft" ? "Edit" : "Open"}
        </button>
      </div>

      {/* Mounted only while open. The panel holds a SendReportButton, which
          fetches the project's saved recipients when its dialog opens — leaving
          collapsed cards unmounted keeps a list of twelve reports from standing
          twelve of those in the tree. */}
      {expanded && (
        <div
          id={panelId}
          className="flex flex-wrap items-center gap-2 border-t border-stone-100 px-3 py-2.5 sm:px-4"
        >
          <button
            onClick={() => download("pdf")}
            disabled={busyKind !== null}
            className={`${BTN_GHOST} px-3 py-1.5 disabled:opacity-40`}
          >
            {busyKind === "pdf" ? (
              <LoaderCircle size={14} className="animate-spin" />
            ) : (
              <FileText size={14} />
            )}
            Standard PDF
          </button>

          <button
            onClick={() => download("xlsx")}
            disabled={busyKind !== null}
            className={`${BTN_GHOST} px-3 py-1.5 disabled:opacity-40`}
          >
            {busyKind === "xlsx" ? (
              <LoaderCircle size={14} className="animate-spin" />
            ) : (
              <Table size={14} />
            )}
            Excel
          </button>

          <button onClick={() => setPreviewOpen(true)} className={`${BTN_GHOST} px-3 py-1.5`}>
            <Eye size={14} /> Preview
          </button>

          {canSend && (
            <SendReportButton
              versionId={version.id}
              periodKey={version.periodKey}
              projectId={projectId}
              label
            />
          )}

          {canDelete && (
            <button
              onClick={onDelete}
              aria-label={`Delete report ${version.periodKey}`}
              title="Delete report"
              className="ml-auto inline-flex items-center justify-center rounded-lg p-1.5 text-stone-400 hover:text-red-600 hover:bg-red-50 transition-colors"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      )}

      <PdfPreviewModal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        versionId={version.id}
        periodKey={version.periodKey}
        projectName={projectName}
        filename={reportFileName({
          projectName,
          periodKey: version.periodKey,
          versionId: version.id,
        })}
        cacheKey={String(version.id)}
      />
    </div>
  );
}
