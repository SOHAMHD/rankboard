/* ════════════════════════════════════════════════════════════════════
   REPORT DOCUMENT — renderers for the generated block document.

   A generated report version carries a BLOCK DOCUMENT in content_json (built
   server-side from the frozen data_json — see report_document.py). This module
   renders that document: header, narrative prose (with inline blob-chips), metric
   grids, GA4/GSC/keyword data tables, the GSC daily-trend chart, and the
   new-backlinks list. Sections whose source wasn't gathered render a clear "not
   available for this period" flag.

   The default export `ReportDocument` renders the whole document READ-ONLY (used
   for locked/sent versions). The individual block components + helpers are also
   EXPORTED so the editable document (ReportDocumentEditor.jsx) renders DATA blocks
   identically — DATA VALUES are never editable, anywhere. Only narrative text is
   editable, and that happens in the editor via the existing TipTap chip editor.

   Number/value formatting reuses the SAME FORMATS table the scalar chip editor
   uses, so display stays consistent across the app. Narrative blocks may carry a
   `doc` (TipTap/ProseMirror JSON, with blob-chips) once edited; we render that
   when present and fall back to the original `paragraphs`/`bullets` otherwise.
   ════════════════════════════════════════════════════════════════════ */
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import {
  TrendingUp,
  TrendingDown,
  Minus,
  ExternalLink,
  Info,
  Link2,
  AlertTriangle,
} from "lucide-react";
import { FORMATS, applyFormat } from "../lib/blobFormats";

// Match the dashboard's chart palette (brand purple + sky).
const COLOR_CLICKS = "#5b5bf7";
const COLOR_IMPRESSIONS = "#0284c7";

// ── value formatting (reuse the chip editor's per-type FORMATS) ───────────────
export function fmtValue(type, value) {
  if (value === null || value === undefined) return "—";
  const t = FORMATS[type] || FORMATS.text;
  const f = (t.value && t.value[0]) || FORMATS.text.value[0];
  try {
    return f.fn(value);
  } catch {
    return String(value);
  }
}

export function fmtDelta(type, value) {
  if (value === null || value === undefined) return null;
  const t = FORMATS[type] || FORMATS.text;
  const f = (t.delta && t.delta[0]) || FORMATS.text.delta[0];
  try {
    return f.fn(value);
  } catch {
    return String(value);
  }
}

// Improvement direction for a delta: rank-like types improve when the number
// goes DOWN; everything else improves when it goes UP. null = flat/no delta.
function deltaImproved(type, delta) {
  if (delta === 0 || delta === null || delta === undefined) return null;
  const lowerIsBetter = type === "rank";
  return lowerIsBetter ? delta < 0 : delta > 0;
}

export function DeltaBadge({ type, delta, className = "" }) {
  const text = fmtDelta(type, delta);
  if (text === null) return null;
  const improved = deltaImproved(type, delta);
  const tone =
    improved === null
      ? "text-stone-400"
      : improved
      ? "text-emerald-600"
      : "text-red-500";
  const Icon = improved === null ? Minus : improved ? TrendingUp : TrendingDown;
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium font-data ${tone} ${className}`}>
      <Icon size={12} /> {text}
    </span>
  );
}

// ── "not available for this period" flag ──────────────────────────────────────
export function UnavailableNote({ reason }) {
  return (
    <p className="text-sm text-stone-500 bg-stone-50 border border-stone-200 rounded-lg px-3 py-2 flex items-center gap-2">
      <Info size={14} className="shrink-0 text-stone-400" />
      {reason || "Not available for this period."}
    </p>
  );
}

function SectionTitle({ children }) {
  return <h3 className="text-base font-bold text-stone-900 font-display mb-2">{children}</h3>;
}

function Card({ children, className = "" }) {
  return (
    <div className={`bg-white border border-stone-200 rounded-xl p-4 sm:p-5 ${className}`}>{children}</div>
  );
}

// ── narrative doc rendering (ProseMirror/TipTap JSON → read-only, chips resolved)
// Mirrors the chip editor's preview: blob nodes resolve to their FROZEN formatted
// value; a chip that can't resolve shows a clear broken marker. Same node types
// the TipTap editor (StarterKit + blob node) produces.
function renderChip(node, blobsByName, key) {
  const { name, kind, format, label } = node.attrs || {};
  const blob = blobsByName?.get(name);
  const resolved = blob ? applyFormat(blob, kind, format) : null;
  if (resolved === null) {
    return (
      <span key={key} className="inline-flex items-center gap-1 rounded bg-red-50 text-red-700 border border-red-200 px-1 text-sm">
        <AlertTriangle size={11} /> {label || name || "unknown"}
      </span>
    );
  }
  return (
    <span key={key} className="font-data font-semibold text-stone-900">
      {resolved}
    </span>
  );
}

function renderDocText(node, key) {
  let el = node.text;
  for (const m of node.marks || []) {
    if (m.type === "bold") el = <strong>{el}</strong>;
    else if (m.type === "italic") el = <em>{el}</em>;
    else if (m.type === "strike") el = <s>{el}</s>;
    else if (m.type === "code") el = <code className="px-1 rounded bg-stone-100 font-data text-sm">{el}</code>;
  }
  return <span key={key}>{el}</span>;
}

function renderDocNode(node, blobsByName, key) {
  switch (node.type) {
    case "paragraph":
      return <p key={key}>{renderDocNodes(node.content, blobsByName, key)}</p>;
    case "heading": {
      const L = node.attrs?.level || 2;
      const Tag = `h${L}`;
      return <Tag key={key}>{renderDocNodes(node.content, blobsByName, key)}</Tag>;
    }
    case "bulletList":
      return <ul key={key}>{renderDocNodes(node.content, blobsByName, key)}</ul>;
    case "orderedList":
      return <ol key={key}>{renderDocNodes(node.content, blobsByName, key)}</ol>;
    case "listItem":
      return <li key={key}>{renderDocNodes(node.content, blobsByName, key)}</li>;
    case "blockquote":
      return <blockquote key={key}>{renderDocNodes(node.content, blobsByName, key)}</blockquote>;
    case "hardBreak":
      return <br key={key} />;
    case "text":
      return renderDocText(node, key);
    case "blob":
      return renderChip(node, blobsByName, key);
    default:
      return node.content ? <span key={key}>{renderDocNodes(node.content, blobsByName, key)}</span> : null;
  }
}

function renderDocNodes(nodes, blobsByName, keyPrefix) {
  if (!nodes) return null;
  return nodes.map((n, i) => renderDocNode(n, blobsByName, `${keyPrefix}-${i}`));
}

// ── block renderers ───────────────────────────────────────────────────────────
export function HeaderBlock({ block }) {
  return (
    <div className="bg-white border border-stone-200 rounded-xl p-5">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-orange-600">{block.title}</p>
      <h2 className="text-xl font-bold text-stone-900 font-display mt-0.5">{block.projectName || "Report"}</h2>
      <p className="text-sm text-stone-500 mt-0.5">
        {block.domain ? <span className="font-data">{block.domain}</span> : null}
        {block.domain ? " · " : ""}
        {block.periodLabel}
        {block.prevPeriodLabel ? <span className="text-stone-400"> (vs. {block.prevPeriodLabel})</span> : null}
      </p>
    </div>
  );
}

export function NarrativeBlock({ block, blobsByName }) {
  const hasDoc = block.doc && block.doc.type === "doc";
  const paragraphs = block.paragraphs || [];
  const bullets = block.bullets || [];
  const empty = !hasDoc && paragraphs.length === 0 && bullets.length === 0;
  return (
    <Card>
      {block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
      <div className="report-prose text-stone-700">
        {hasDoc ? (
          renderDocNodes(block.doc.content, blobsByName, "n")
        ) : (
          <>
            {paragraphs.map((p, i) => (
              <p key={`p-${i}`}>{p}</p>
            ))}
            {bullets.length > 0 && (
              <ul>
                {bullets.map((b, i) => (
                  <li key={`b-${i}`}>{b}</li>
                ))}
              </ul>
            )}
            {empty && <p className="text-stone-400">—</p>}
          </>
        )}
      </div>
    </Card>
  );
}

export function MetricGridBlock({ block }) {
  return (
    <Card>
      <SectionTitle>{block.title}</SectionTitle>
      {block.available === false ? (
        <UnavailableNote reason={block.unavailableReason} />
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {(block.metrics || []).map((m) => (
            <div key={m.key} className="rounded-lg border border-stone-200 bg-stone-50/60 px-3 py-2.5">
              <p className="text-xs text-stone-500">{m.label}</p>
              <p className="text-lg font-bold text-stone-900 font-data leading-tight mt-0.5">
                {fmtValue(m.type, m.currentValue)}
              </p>
              <div className="mt-0.5 min-h-[1rem]">
                <DeltaBadge type={m.type} delta={m.deltaValue} />
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

function cell(col, cells) {
  const v = cells ? cells[col.key] : undefined;
  if (col.kind === "dim") {
    return <span className="text-stone-700">{v === null || v === undefined || v === "" ? "—" : String(v)}</span>;
  }
  if (col.kind === "delta") {
    return <DeltaBadge type={col.type} delta={v} />;
  }
  return <span className="font-data text-stone-800">{fmtValue(col.type, v)}</span>;
}

export function DataTableBlock({ block }) {
  const columns = block.columns || [];
  const rows = block.rows || [];
  return (
    <Card>
      <SectionTitle>{block.title}</SectionTitle>
      {block.available === false ? (
        <UnavailableNote reason={block.unavailableReason} />
      ) : rows.length === 0 ? (
        <p className="text-sm text-stone-400 py-2">No data for this period.</p>
      ) : (
        <div className="overflow-x-auto -mx-1">
          <table className="w-full text-sm border-collapse">
            <thead>
              <tr className="border-b border-stone-200">
                {columns.map((c) => (
                  <th
                    key={c.key}
                    className={`py-2 px-2 text-xs font-semibold uppercase tracking-wider text-stone-400 ${
                      c.kind === "dim" ? "text-left" : "text-right"
                    }`}
                  >
                    {c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={i} className="border-b border-stone-100 last:border-0">
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={`py-1.5 px-2 ${c.kind === "dim" ? "text-left max-w-[18rem] truncate" : "text-right"}`}
                    >
                      {cell(c, r.cells)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function ChartBlock({ block }) {
  const points = block.points || [];
  return (
    <Card>
      <SectionTitle>{block.title}</SectionTitle>
      {block.available === false || points.length === 0 ? (
        <UnavailableNote reason={block.unavailableReason} />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={points} margin={{ top: 5, right: 8, left: -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f5" vertical={false} />
            <XAxis dataKey="x" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={{ stroke: "#e7eaf0" }} minTickGap={24} />
            <YAxis yAxisId="left" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
            <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={false} allowDecimals={false} width={48} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #e7eaf0", boxShadow: "0 4px 16px rgba(18,24,38,0.08)" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
            <Line yAxisId="left" type="monotone" dataKey="clicks" name="Clicks" stroke={COLOR_CLICKS} strokeWidth={2.5} dot={false} activeDot={{ r: 4 }} />
            <Line yAxisId="right" type="monotone" dataKey="impressions" name="Impressions" stroke={COLOR_IMPRESSIONS} strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

export function BacklinksBlock({ block }) {
  const items = block.items || [];
  return (
    <Card>
      <SectionTitle>{block.title}</SectionTitle>
      {items.length === 0 ? (
        <p className="text-sm text-stone-400 py-1">No new backlinks recorded for this period.</p>
      ) : (
        <>
          <p className="text-xs text-stone-500 mb-2">
            <span className="font-data font-semibold text-stone-700">{block.count}</span> new backlink{block.count === 1 ? "" : "s"} this period
          </p>
          <ol className="space-y-1.5">
            {items.map((it, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span className="text-xs text-stone-400 font-data mt-0.5 w-5 shrink-0 text-right">{i + 1}.</span>
                <Link2 size={13} className="shrink-0 text-stone-300 mt-1" />
                {it.url ? (
                  <a
                    href={it.url}
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-orange-700 hover:underline break-all inline-flex items-start gap-1"
                  >
                    {it.url}
                    <ExternalLink size={11} className="shrink-0 mt-1 text-stone-300" />
                  </a>
                ) : (
                  <span className="text-stone-400">—</span>
                )}
              </li>
            ))}
          </ol>
        </>
      )}
    </Card>
  );
}

// One block, read-only, dispatched by type. blobsByName resolves narrative chips.
export function Block({ block, blobsByName }) {
  switch (block.type) {
    case "report_header":
      return <HeaderBlock block={block} />;
    case "narrative":
      return <NarrativeBlock block={block} blobsByName={blobsByName} />;
    case "metric_grid":
      return <MetricGridBlock block={block} />;
    case "data_table":
      return <DataTableBlock block={block} />;
    case "chart":
      return <ChartBlock block={block} />;
    case "backlinks_list":
      return <BacklinksBlock block={block} />;
    default:
      return null;
  }
}

// ════════════════════════════════════════════════════════════════════
// ENTRY — renders a version's block document READ-ONLY (locked/sent versions,
// or any non-editable view). Falls back to a friendly note if the version has
// no block document (e.g. a legacy draft).
// ════════════════════════════════════════════════════════════════════
export default function ReportDocument({ version, blobs }) {
  const doc = version?.content;
  const blocks = doc && doc.type === "report_document" ? doc.blocks || [] : null;
  const blobsByName = new Map((blobs || []).map((b) => [b.name, b]));

  if (!blocks) {
    return (
      <p className="text-sm text-stone-500 bg-white border border-stone-200 rounded-xl p-6">
        This version has no rendered report document.
      </p>
    );
  }

  return (
    <div className="w-full max-w-4xl">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-stone-100 text-stone-600">
          {version.status}
        </span>
        <span className="text-xs text-stone-400">#{version.id} · read-only</span>
      </div>
      <div className="space-y-4">
        {blocks.map((b) => (
          <Block key={b.id} block={b} blobsByName={blobsByName} />
        ))}
      </div>
    </div>
  );
}
