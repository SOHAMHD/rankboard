import { api } from "./api";

const lists = new Map();
const queries = new Map();

function search(kind, { q = "", country, region, limit } = {}) {
  const params = new URLSearchParams({ kind, q });
  if (country != null) params.set("country", country);
  if (region != null) params.set("region", region);
  if (limit != null) params.set("limit", limit);
  return api(`/locations/search?${params}`).then((d) => d.locations);
}

function cached(store, key, load) {
  if (!store.has(key)) store.set(key, load().catch((err) => (store.delete(key), Promise.reject(err))));
  return store.get(key);
}

// ~250 rows, so fetching the lot once and filtering locally is genuinely cheaper
// than a request per keystroke.
export const listCountries = () => cached(lists, "c", () => search("country", { limit: 500 }));

/** First 25 regions for a country — what the dropdown shows before typing. */
export const listRegions = (countryCode) =>
  countryCode == null
    ? Promise.resolve([])
    : cached(lists, `r${countryCode}`, () => search("region", { country: countryCode, limit: 25 }));

/**
 * Region search, server-side — same shape as searchCities.
 *
 * This used to pull up to 5000 regions per country and filter them in the browser
 * with filterLocal on every keystroke, including a Levenshtein pass that
 * allocated a DP matrix per row. That was hundreds of milliseconds of blocked
 * main thread per character. The server already does indexed prefix + token
 * matching for exactly this, which is what cities have always used.
 */
export function searchRegions(q, { country } = {}) {
  if (country == null) return Promise.resolve([]);
  const term = q.trim();
  if (!term) return listRegions(country);
  const key = `r|${country}|${term.toLowerCase()}`;
  if (queries.size > 300) queries.clear();
  return cached(queries, key, () => search("region", { q: term, country, limit: 25 }));
}

export function searchCities(q, { country, region } = {}) {
  const key = `${country ?? ""}|${region ?? ""}|${q.trim().toLowerCase()}`;
  if (queries.size > 300) queries.clear();
  return cached(queries, key, () => search("city", { q, country, region, limit: 25 }));
}

export const resolveLocation = (code) => api(`/locations/resolve?code=${encodeURIComponent(code)}`);

export const locationsStatus = () => api("/locations/status");

function distance(a, b, max) {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const row = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      row[j] = Math.min(
        prev[j] + 1,
        row[j - 1] + 1,
        prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
      best = Math.min(best, row[j]);
    }
    if (best > max) return max + 1;
    prev = row;
  }
  return prev[b.length];
}

//: Lowercased name + haystack, computed once per row object and reused across
//: keystrokes. Previously every keystroke rebuilt these strings for every row:
//: three toLowerCase calls and a concatenation each.
const _hay = new WeakMap();

function haystack(r) {
  let cached = _hay.get(r);
  if (cached === undefined) {
    const name = String(r.name || "").toLowerCase();
    cached = { name, hay: `${name} ${(r.alt || "").toLowerCase()} ${(r.fullName || "").toLowerCase()}` };
    _hay.set(r, cached);
  }
  return cached;
}

export function filterLocal(rows, query, limit = 25) {
  const q = query.trim().toLowerCase().replace(/\s+/g, " ");
  if (!q) return rows.slice(0, limit);

  // Hoisted out of the loop — this was being recomputed once per row.
  const tokens = q.includes(" ") ? q.split(" ") : null;
  const spaced = ` ${q}`;

  const scored = [];
  for (const r of rows) {
    const { name, hay } = haystack(r);
    let rank = -1;
    if (name.startsWith(q)) rank = 0;
    else if (hay.includes(spaced)) rank = 1;
    else if (hay.includes(q)) rank = 2;
    else if (tokens && tokens.every((t) => hay.includes(t))) rank = 3;
    if (rank >= 0) scored.push([rank, r.name.length, r]);
  }

  if (!scored.length && q.length >= 4) {
    const slack = q.length > 7 ? 2 : 1;
    for (const r of rows) {
      const d = distance(q, haystack(r).name, slack);
      if (d <= slack) scored.push([4 + d, r.name.length, r]);
    }
  }

  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2].name.localeCompare(b[2].name));
  return scored.slice(0, limit).map((s) => s[2]);
}
