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

export const listCountries = () => cached(lists, "c", () => search("country", { limit: 500 }));

export const listRegions = (countryCode) =>
  countryCode == null
    ? Promise.resolve([])
    : cached(lists, `r${countryCode}`, () => search("region", { country: countryCode, limit: 5000 }));

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

export function filterLocal(rows, query, limit = 25) {
  const q = query.trim().toLowerCase().replace(/\s+/g, " ");
  if (!q) return rows.slice(0, limit);

  const scored = [];
  for (const r of rows) {
    const name = r.name.toLowerCase();
    const hay = `${name} ${(r.alt || "").toLowerCase()} ${(r.fullName || "").toLowerCase()}`;
    let rank = -1;
    if (name.startsWith(q)) rank = 0;
    else if (hay.includes(` ${q}`)) rank = 1;
    else if (hay.includes(q)) rank = 2;
    else if (q.split(" ").every((t) => hay.includes(t))) rank = 3;
    if (rank >= 0) scored.push([rank, r.name.length, r]);
  }

  if (!scored.length && q.length >= 4) {
    const slack = q.length > 7 ? 2 : 1;
    for (const r of rows) {
      const d = distance(q, r.name.toLowerCase(), slack);
      if (d <= slack) scored.push([4 + d, r.name.length, r]);
    }
  }

  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2].name.localeCompare(b[2].name));
  return scored.slice(0, limit).map((s) => s[2]);
}
