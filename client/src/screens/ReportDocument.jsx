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

const COLOR_CLICKS = "#5b5bf7";
const COLOR_IMPRESSIONS = "#0284c7";

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

export function HeaderBlock({ block }) {
  return (
    <div className="bg-white border border-stone-200 rounded-xl p-5">
      {block.clientLogo ? (
        <img src={block.clientLogo} alt="Client logo" className="h-10 mb-2 object-contain" />
      ) : null}
      <p className="text-[11px] font-semibold uppercase tracking-wider text-orange-600">{block.title}</p>
      <h2 className="text-xl font-bold text-stone-900 font-display mt-0.5">{block.projectName || "Report"}</h2>
      <p className="text-sm text-stone-500 mt-0.5">
        {block.domain ? <span className="font-data">{block.domain}</span> : null}
        {block.domain ? " · " : ""}
        {block.periodLabel}
        {block.prevPeriodLabel ? <span className="text-stone-400"> (vs. {block.prevPeriodLabel})</span> : null}
      </p>
      {block.maturing ? (
        <p className="mt-3 text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 flex items-center gap-2">
          <AlertTriangle size={14} className="shrink-0 text-amber-500" />
          {block.maturingNotice || "This month is still in progress — data is still maturing."}
        </p>
      ) : null}
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

export function MetricGridBlock({ block, hideTitle }) {
  return (
    <Card>
      {!hideTitle && block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
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

export const rowIncluded = (r) => !r || r.included !== false;

function RowSelectBar({ total, selected, onBulk }) {
  const Btn = ({ mode, children }) => (
    <button
      type="button"
      onClick={() => onBulk(mode)}
      className="px-2 py-0.5 rounded-md border border-stone-200 text-stone-600 hover:bg-orange-50 hover:text-orange-700 hover:border-orange-200 transition-colors"
    >
      {children}
    </button>
  );
  return (
    <div className="flex flex-wrap items-center gap-1.5 mb-2 text-xs">
      <span className="text-stone-400 mr-0.5">Rows:</span>
      <Btn mode={5}>Top 5</Btn>
      <Btn mode={10}>Top 10</Btn>
      <Btn mode="all">All</Btn>
      <Btn mode="none">None</Btn>
      <span className="ml-auto text-stone-500 font-data">
        {selected} of {total} selected
      </span>
    </div>
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

export function DataTableBlock({
  block,
  selectable = false,
  onToggleRow,
  onBulk,
  hideTitle,
  editable = false,
  onCellChange,
}) {
  const columns = block.columns || [];
  const allRows = block.rows || [];
  const rows = selectable ? allRows : allRows.filter(rowIncluded);
  const selectedCount = allRows.filter(rowIncluded).length;
  return (
    <Card>
      {!hideTitle && block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
      {block.available === false ? (
        <UnavailableNote reason={block.unavailableReason} />
      ) : allRows.length === 0 ? (
        <p className="text-sm text-stone-400 py-2">No data for this period.</p>
      ) : !selectable && rows.length === 0 ? (
        <p className="text-sm text-stone-400 py-2">No rows selected.</p>
      ) : (
        <>
          {selectable && (
            <RowSelectBar total={allRows.length} selected={selectedCount} onBulk={onBulk} />
          )}
          <div className="overflow-x-auto -mx-1">
            <table className="w-full text-sm border-collapse">
              <thead>
                <tr className="border-b border-stone-200">
                  {selectable && <th className="w-8 py-2 px-2" aria-label="Include row" />}
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
                {rows.map((r, i) => {
                  const included = rowIncluded(r);
                  return (
                    <tr
                      key={i}
                      className={`border-b border-stone-100 last:border-0 ${
                        selectable && !included ? "opacity-40" : ""
                      }`}
                    >
                      {selectable && (
                        <td className="py-1.5 px-2 align-middle">
                          <input
                            type="checkbox"
                            checked={included}
                            onChange={(e) => onToggleRow(i, e.target.checked)}
                            className="accent-orange-600 cursor-pointer"
                            aria-label="Include this row in the report"
                          />
                        </td>
                      )}
                      {columns.map((c) => {
                        if (editable) {
                          const raw = (r.cells || {})[c.key];
                          const isDim = c.kind === "dim";
                          return (
                            <td key={c.key} className="py-1 px-2">
                              <input
                                value={raw === null || raw === undefined ? "" : String(raw)}
                                onChange={(e) => onCellChange?.(i, c.key, e.target.value)}
                                inputMode={isDim ? "text" : "numeric"}
                                placeholder={isDim ? "" : "—"}
                                aria-label={`${c.label}${isDim ? "" : ` for row ${i + 1}`}`}
                                className={`rounded-md border border-stone-200 px-2 py-1 text-sm text-stone-900
                                  focus:outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 transition-colors
                                  ${isDim ? "w-full text-left" : "w-16 text-center font-data"}`}
                              />
                            </td>
                          );
                        }
                        return (
                          <td
                            key={c.key}
                            className={`py-1.5 px-2 ${c.kind === "dim" ? "text-left max-w-[18rem] truncate" : "text-right"}`}
                          >
                            {cell(c, r.cells)}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Card>
  );
}

export function ChartBlock({ block, hideTitle }) {
  const points = block.points || [];
  const series =
    block.series && block.series.length
      ? block.series
      : [
          { key: "clicks", label: "Clicks", type: "count" },
          { key: "impressions", label: "Impressions", type: "count" },
        ];
  const palette = [COLOR_CLICKS, COLOR_IMPRESSIONS, "#15b41f", "#e0362c"];
  const multi = series.length > 2;
  const dual = series.length === 2;
  return (
    <Card>
      {!hideTitle && block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
      {block.available === false || points.length === 0 ? (
        <UnavailableNote reason={block.unavailableReason} />
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <LineChart data={points} margin={{ top: 5, right: 8, left: multi ? 0 : -8, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f5" vertical={false} />
            <XAxis dataKey="x" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={{ stroke: "#e7eaf0" }} minTickGap={24} />
            {multi ? (
              series.map((s) => (
                <YAxis key={s.key} yAxisId={s.key} hide domain={["auto", "auto"]} />
              ))
            ) : (
              <>
                <YAxis yAxisId="left" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={false} allowDecimals={false} width={44} />
                {dual && (
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11, fill: "#99a1b0" }} tickLine={false} axisLine={false} allowDecimals={false} width={48} />
                )}
              </>
            )}
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 12, border: "1px solid #e7eaf0", boxShadow: "0 4px 16px rgba(18,24,38,0.08)" }} />
            <Legend wrapperStyle={{ fontSize: 12 }} iconType="circle" />
            {series.map((s, i) => (
              <Line
                key={s.key}
                yAxisId={multi ? s.key : dual && i === 1 ? "right" : "left"}
                type="monotone"
                dataKey={s.key}
                name={s.label || s.key}
                stroke={palette[i % palette.length]}
                strokeWidth={2.3}
                dot={false}
                activeDot={{ r: 4 }}
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      )}
    </Card>
  );
}

export function BacklinksBlock({ block, selectable = false, onToggleRow, onBulk, hideTitle }) {
  const allItems = block.items || [];
  const items = selectable ? allItems : allItems.filter(rowIncluded);
  const selectedCount = allItems.filter(rowIncluded).length;
  const total = block.count;
  const noun = block.noun || "backlink";
  if (allItems.length === 0) {
    return (
      <Card>
        {!hideTitle && block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
        <p className="text-sm text-stone-400 py-1">No {noun}s recorded for this period.</p>
      </Card>
    );
  }
  return (
    <Card>
      {!hideTitle && block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
      <p className="text-xs text-stone-500 mb-2">
        <span className="font-data font-semibold text-stone-700">{total}</span> {noun}
        {total === 1 ? "" : "s"} this period
        {selectedCount !== total ? (
          <span> · showing {selectedCount} of {total}</span>
        ) : null}
      </p>
      {selectable && (
        <RowSelectBar total={allItems.length} selected={selectedCount} onBulk={onBulk} />
      )}
      {items.length === 0 ? (
        <p className="text-sm text-stone-400 py-1">No backlinks selected.</p>
      ) : (
        <ol className="space-y-1.5">
          {items.map((it, i) => {
            const included = rowIncluded(it);
            return (
              <li
                key={i}
                className={`flex items-start gap-2 text-sm ${
                  selectable && !included ? "opacity-40" : ""
                }`}
              >
                {selectable && (
                  <input
                    type="checkbox"
                    checked={included}
                    onChange={(e) => onToggleRow(i, e.target.checked)}
                    className="accent-orange-600 cursor-pointer mt-1 shrink-0"
                    aria-label="Include this backlink in the report"
                  />
                )}
                <span className="text-xs text-stone-400 font-data mt-0.5 w-5 shrink-0 text-right">{i + 1}.</span>
                <Link2 size={13} className="shrink-0 text-stone-300 mt-1" />
                <span className="min-w-0">
                  {it.title ? (
                    <span className="block font-medium text-stone-800">{it.title}</span>
                  ) : null}
                  {it.url ? (
                    <a
                      href={/^https?:\/\//i.test(it.url) ? it.url : undefined}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="text-orange-700 hover:underline break-all inline-flex items-start gap-1"
                    >
                      {it.url}
                      <ExternalLink size={11} className="shrink-0 mt-1 text-stone-300" />
                    </a>
                  ) : !it.title ? (
                    <span className="text-stone-400">—</span>
                  ) : null}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

export function TargetsGridBlock({ block, hideTitle }) {
  const columns = block.columns || [];
  const fields = block.fields || [];
  const values = block.values || {};
  return (
    <Card>
      {!hideTitle && block.title ? <SectionTitle>{block.title}</SectionTitle> : null}
      {columns.map((col, ci) => (
        <div
          key={col.key}
          className={ci < columns.length - 1 ? "mb-4 pb-4 border-b-2 border-blue-600" : ""}
        >
          <h4 className="text-sm font-semibold text-blue-700 mb-2">{col.label}</h4>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {fields.map((f) => {
              const v = (values[col.key] || {})[f.key];
              const shown = v === null || v === undefined || v === "" ? "\u2014" : String(v);
              return (
                <div key={f.key}>
                  <p className="text-xs text-stone-500 underline">{f.label}</p>
                  <p className="text-lg font-bold text-blue-700 font-data leading-tight mt-0.5">{shown}</p>
                </div>
              );
            })}
          </div>
        </div>
      ))}
      {block.notes ? (
        <p className="report-prose text-stone-700 mt-3 whitespace-pre-wrap">{block.notes}</p>
      ) : null}
    </Card>
  );
}

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
    case "targets_grid":
      return <TargetsGridBlock block={block} />;
    default:
      return null;
  }
}

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
