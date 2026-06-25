/* ════════════════════════════════════════════════════════════════════
   BLOB FORMATS — per-TYPE display formats for inserted data blobs.

   Each blob has a TYPE (count / duration / percent / rank / text), a
   current value, and (sometimes) a delta. A chip stores { name, kind, format }
   where kind is "value" (the current value) or "delta" (the month-over-month
   change). Formats are defined ONCE per type here (not per blob); a chip just
   stores which format id it chose. Format changes affect DISPLAY only — never
   the underlying frozen value.

   DELTA SIGN CONVENTION (matches the backend _delta): deltas are stored RAW as
   current − previous. For RANK-like types (rank, avg position) a NEGATIVE delta
   is an IMPROVEMENT (the position number got smaller); for count/percent/
   duration a POSITIVE delta is growth. The directional formats below respect
   this — they never invert the stored number, they present its direction
   correctly (a −2 rank delta reads "up 2", an improvement).

   PERCENT values are stored as FRACTIONS (0–1, e.g. GSC ctr 0.0631), so percent
   formats multiply by 100 for display.
   ════════════════════════════════════════════════════════════════════ */

export const KIND = { VALUE: "value", DELTA: "delta" };

// Types where a SMALLER number is better, so a negative delta = improvement.
const LOWER_IS_BETTER = new Set(["rank"]);

// ── number helpers ───────────────────────────────────────────────────
const round = (n, d = 0) => {
  const f = Math.pow(10, d);
  return Math.round(Number(n) * f) / f;
};
const grouped = (n) => Number(n).toLocaleString("en-US");
const compact = (n, digits) =>
  new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: digits })
    .format(Number(n))
    .toLowerCase();
const sign = (v) => (v > 0 ? "+" : ""); // negatives already carry "-"
const ordinal = (n) => {
  const s = ["th", "st", "nd", "rd"];
  const v = Math.abs(Math.round(n)) % 100;
  return `${n}${s[(v - 20) % 10] || s[v] || s[0]}`;
};
// Directional words for a delta, given whether lower-is-better for this type.
const direction = (v, lowerIsBetter) => {
  if (v === 0) return "no change";
  const improved = lowerIsBetter ? v < 0 : v > 0;
  return improved ? "up" : "down";
};

// ── format tables (defined ONCE per type) ────────────────────────────
// Each format: { id, name, fn(value) -> string }. For kind "delta", fn
// receives the delta number; directional formats know the type's convention.
export const FORMATS = {
  count: {
    value: [
      { id: "grouped", name: "Grouped", fn: (v) => grouped(Math.round(v)) },     // 4,983
      { id: "compact1", name: "Compact", fn: (v) => compact(v, 1) },              // 5k
      { id: "compact2", name: "Compact (precise)", fn: (v) => compact(v, 2) },    // 4.98k
      { id: "plain", name: "Plain", fn: (v) => String(Math.round(v)) },           // 4983
    ],
    delta: [
      { id: "signedGrouped", name: "Signed", fn: (v) => sign(v) + grouped(Math.round(v)) }, // +1,250
      { id: "signedCompact", name: "Signed compact", fn: (v) => sign(v) + compact(v, 1) },  // +1.3k
      { id: "grouped", name: "Grouped", fn: (v) => grouped(Math.round(v)) },                // 1,250
    ],
  },
  duration: {
    value: [
      { id: "seconds", name: "Seconds", fn: (v) => `${round(v)}s` },              // 47s
      { id: "minutes", name: "Minutes", fn: (v) => `${round(v / 60, 1)} min` },   // 0.8 min
      { id: "clock", name: "Clock", fn: (v) => `${Math.floor(v / 60)}m ${round(v % 60)}s` }, // 0m 47s
    ],
    delta: [
      { id: "signedSeconds", name: "Signed seconds", fn: (v) => `${sign(v)}${round(v, 1)}s` }, // +0.4s
      { id: "signedMinutes", name: "Signed minutes", fn: (v) => `${sign(v)}${round(v / 60, 1)} min` },
    ],
  },
  percent: {
    value: [
      { id: "pct2", name: "0.00%", fn: (v) => `${round(v * 100, 2)}%` },          // 6.31%
      { id: "pct0", name: "0%", fn: (v) => `${round(v * 100)}%` },                // 6%
    ],
    delta: [
      { id: "signedPct", name: "Signed", fn: (v) => `${sign(v)}${round(v * 100, 2)}%` },        // +0.45%
      { id: "wordedPct", name: "Worded", fn: (v) => (v === 0 ? "no change" : `${direction(v, false)} ${Math.abs(round(v * 100, 2))}%`) }, // up 0.45%
      { id: "signedPct0", name: "Signed (0)", fn: (v) => `${sign(v)}${round(v * 100)}%` },       // +12%
    ],
  },
  rank: {
    value: [
      { id: "hash", name: "#1", fn: (v) => `#${round(v)}` },                      // #1
      { id: "ordinal", name: "1st", fn: (v) => ordinal(round(v)) },              // 1st
      { id: "word", name: "rank 1", fn: (v) => `rank ${round(v)}` },             // rank 1
    ],
    // RANK deltas: negative = improvement. Directional formats read a −2 as
    // "up 2" / "▲2" WITHOUT inverting the stored number; the signed format
    // shows the literal value.
    delta: [
      { id: "worded", name: "Worded", fn: (v) => (v === 0 ? "no change" : `${direction(v, true)} ${Math.abs(round(v, 1))}`) }, // up 2
      { id: "arrow", name: "Arrow", fn: (v) => (v === 0 ? "0" : `${v < 0 ? "▲" : "▼"}${Math.abs(round(v, 1))}`) },             // ▲2
      { id: "signed", name: "Signed (raw)", fn: (v) => `${sign(v)}${round(v, 1)}` },                                            // -2
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

/** The value a chip resolves against for a given kind (current vs delta). */
export function valueForKind(blob, kind) {
  if (!blob) return null;
  const v = kind === KIND.DELTA ? blob.deltaValue : blob.currentValue;
  return v === undefined ? null : v;
}

/** The sensible DEFAULT format id for a (type, kind) — the first defined. */
export function defaultFormatId(type, kind) {
  const list = formatList(type, kind);
  return list.length ? list[0].id : "asis";
}

/** Format option chips for the picker — each with a SAMPLE computed from the
 *  blob's real value, so the author sees exactly what they'd get. */
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

/** Resolve a chip to its formatted string, or NULL when it can't resolve
 *  (blob missing from the frozen data, or no value for this kind). NULL is the
 *  "broken blob" signal the editor/preview/finalize-guard key off. */
export function applyFormat(blob, kind, formatId) {
  const v = valueForKind(blob, kind);
  if (v === null || v === undefined) return null; // unresolved
  const list = formatList(blob.type, kind);
  const f = list.find((x) => x.id === formatId) || list[0];
  if (!f) return String(v);
  try {
    return f.fn(v);
  } catch {
    return String(v);
  }
}

/** Editor-surface label for a chip (shows the field NAME, not the value). */
export function chipLabel(blob, kind, fallbackLabel) {
  const base = blob?.label || fallbackLabel || "(unknown)";
  return kind === KIND.DELTA ? `${base} change` : base;
}
