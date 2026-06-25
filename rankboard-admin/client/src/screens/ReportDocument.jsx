/* ════════════════════════════════════════════════════════════════════
   REPORT DOCUMENT — read-only renderer for the generated block document.

   A generated report version now carries a BLOCK DOCUMENT in content_json
   (built server-side from the frozen data_json — see report_document.py). This
   component renders that document as the full, templated report: header,
   narrative prose, metric grids, GA4/GSC/keyword data tables, the GSC daily-trend
   chart, and the new-backlinks list. Sections whose source wasn't gathered for
   the period render a clear "not available for this period" flag.

   READ-ONLY for this slice: there are NO editing controls (add/delete/reorder,
   text edits, cell edits) — those arrive in the next slice. Data VALUES are
   immutable (seeded from the frozen blob); only narrative prose will become
   editable later. Number/value formatting reuses the same FORMATS table the
   scalar chip editor uses, so display stays consistent across the app.
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
} from "lucide-react";
import { FORMATS } from "../lib/blobFormats";

// Match the dashboard's chart palette (brand purple + sky).
const COLOR_CLICKS = "#5b5bf7";
const COLOR_IMPRESSIONS = "#0284c7";

// ── value formatting (reuse the chip editor's per-type FORMATS) ───────────────
function fmtValue(type, value) {
  if (value === null || value === undefined) return "—";
  const t = FORMATS[type] || FORMATS.text;
  const f = (t.value && t.value[0]) || FORMATS.text.value[0];
  try {
    return f.fn(value);
  } catch {
    return String(value);
  }
}

function fmtDelta(type, value) {
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

function DeltaBadge({ type, delta, className = "" }) {
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
function UnavailableNote({ reason }) {
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

// ── block renderers ───────────────────────────────────────────────────────────
function HeaderBlock({ block }) {
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

function NarrativeBlock({ block }) {
  const paragraphs = block.paragraphs || [];
  const bullets = block.bullets || [];
  return (
    <Card>
      <SectionTitle>{block.title}</SectionTitle>
      <div className="report-prose text-stone-700">
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
        {paragraphs.length === 0 && bullets.length === 0 && (
          <p className="text-stone-400">—</p>
        )}
      </div>
    </Card>
  );
}

function MetricGridBlock({ block }) {
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

function DataTableBlock({ block }) {
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

function ChartBlock({ block }) {
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

function BacklinksBlock({ block }) {
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

function Block({ block }) {
  switch (block.type) {
    case "report_header":
      return <HeaderBlock block={block} />;
    case "narrative":
      return <NarrativeBlock block={block} />;
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
// ENTRY — renders a version's block document read-only. Falls back to a
// friendly note if the version has no block document (e.g. a legacy draft).
// ════════════════════════════════════════════════════════════════════
export default function ReportDocument({ version }) {
  const doc = version?.content;
  const blocks = doc && doc.type === "report_document" ? doc.blocks || [] : null;

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
          <Block key={b.id} block={b} />
        ))}
      </div>
    </div>
  );
}
