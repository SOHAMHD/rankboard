export const KIND = { VALUE: "value", DELTA: "delta" };

const LOWER_IS_BETTER = new Set(["rank"]);

const round = (n, d = 0) => {
  const f = Math.pow(10, d);
  return Math.round(Number(n) * f) / f;
};
const grouped = (n) => Number(n).toLocaleString("en-US");
const compact = (n, digits) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: digits })
    .format(Number(n))
    .toLowerCase();
const sign = (v) => (v > 0 ? "+" : "");
const humanDuration = (v, signed = false) => {
  const total = Math.round(Math.abs(Number(v) || 0));
  const m = Math.floor(total / 60);
  const s = total % 60;
  const body = m === 0 ? `${s}s` : s === 0 ? `${m}m` : `${m}m ${s}s`;
  const prefix = Number(v) < 0 ? "-" : signed && Number(v) > 0 ? "+" : "";
  return prefix + body;
};
const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"];
  const v = Math.abs(Math.round(n)) % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};
const direction = (v, lowerIsBetter) => {
  if (v === 0) return "no change";
  const improved = lowerIsBetter ? v < 0 : v > 0;
  return improved ? "up" : "down";
};

export const FORMATS = {
  count: {
    value: [
      { id: "grouped", name: "Grouped", fn: (v) => grouped(Math.round(v)) },
      { id: "compact1", name: "Compact", fn: (v) => compact(v, 1) },
      { id: "compact2", name: "Compact (precise)", fn: (v) => compact(v, 2) },
      { id: "plain", name: "Plain", fn: (v) => String(Math.round(v)) },
    ],
    delta: [
      { id: "signedGrouped", name: "Signed", fn: (v) => sign(v) + grouped(Math.round(v)) },
      { id: "signedCompact", name: "Signed compact", fn: (v) => sign(v) + compact(v, 1) },
      { id: "grouped", name: "Grouped", fn: (v) => grouped(Math.round(v)) },
    ],
  },
  duration: {
    value: [
      { id: "auto", name: "Auto (s under 1m)", fn: (v) => humanDuration(v) },
      { id: "seconds", name: "Seconds", fn: (v) => `${round(v)}s` },
      { id: "minutes", name: "Minutes", fn: (v) => `${round(v / 60, 1)} min` },
      { id: "clock", name: "Clock", fn: (v) => `${Math.floor(v / 60)}m ${round(v % 60)}s` },
    ],
    delta: [
      { id: "signedAuto", name: "Signed auto", fn: (v) => humanDuration(v, true) },
      { id: "signedSeconds", name: "Signed seconds", fn: (v) => `${sign(v)}${round(v, 1)}s` },
      { id: "signedMinutes", name: "Signed minutes", fn: (v) => `${sign(v)}${round(v / 60, 1)} min` },
    ],
  },
  percent: {
    value: [
      { id: "pct2", name: "0.00%", fn: (v) => `${round(v * 100, 2)}%` },
      { id: "pct0", name: "0%", fn: (v) => `${round(v * 100)}%` },
    ],
    delta: [
      { id: "signedPct", name: "Signed", fn: (v) => `${sign(v)}${round(v * 100, 2)}%` },
      { id: "wordedPct", name: "Worded", fn: (v) => (v === 0 ? "no change" : `${direction(v, false)} ${Math.abs(round(v * 100, 2))}%`) },
      { id: "signedPct0", name: "Signed (0)", fn: (v) => `${sign(v)}${round(v * 100)}%` },
    ],
  },
  rank: {
    value: [
      { id: "hash", name: "#1", fn: (v) => `#${round(v)}` },
      { id: "ordinal", name: "1st", fn: (v) => ordinal(round(v)) },
      { id: "word", name: "rank 1", fn: (v) => `rank ${round(v)}` },
    ],
    delta: [
      { id: "worded", name: "Worded", fn: (v) => (v === 0 ? "no change" : `${direction(v, true)} ${Math.abs(round(v, 1))}`) },
      { id: "arrow", name: "Arrow", fn: (v) => (v === 0 ? "0" : `${v < 0 ? "▲" : "▼"}${Math.abs(round(v, 1))}`) },
      { id: "signed", name: "Signed (raw)", fn: (v) => `${sign(v)}${round(v, 1)}` },
    ],
  },
  text: {
    value: [{ id: "asis", name: "As-is", fn: (v) => String(v) }],
    delta: [{ id: "asis", name: "As-is", fn: (v) => String(v) }],
  },
};

function formatList(type, kind) {
  const t = FORMATS[type] || FORMATS.text;
  return t[kind] || t.value || [];
}

export function valueForKind(blob, kind) {
  if (!blob) return null;
  const v = kind === KIND.DELTA ? blob.deltaValue : blob.currentValue;
  return v === undefined ? null : v;
}

export function defaultFormatId(type, kind) {
  const list = formatList(type, kind);
  return list.length ? list[0].id : "asis";
}

export function formatOptions(blob, kind) {
  const v = valueForKind(blob, kind);
  return formatList(blob?.type, kind).map((f) => {
    let sample;
    try {
      sample = v === null || v === undefined ? "—" : f.fn(v);
    } catch {
      sample = "—";
    }
    return { id: f.id, name: f.name, sample };
  });
}

export function applyFormat(blob, kind, formatId) {
  const v = valueForKind(blob, kind);
  if (v === null || v === undefined) return null;
  const list = formatList(blob.type, kind);
  const f = list.find((x) => x.id === formatId) || list[0];
  if (!f) return String(v);
  try {
    return f.fn(v);
  } catch {
    return String(v);
  }
}

export function chipLabel(blob, kind, fallbackLabel) {
  const base = blob?.label || fallbackLabel || "(unknown)";
  return kind === KIND.DELTA ? `${base} change` : base;
}
