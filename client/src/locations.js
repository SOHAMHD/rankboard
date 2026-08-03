/* GEO LOOKUPS — the data behind the project picker's Country / Region / City
   type-ahead inputs.

   This used to bundle a small hand-written seed file at build time. It can't any
   more: the picker now covers every country, region and city DataForSEO
   supports (~100k rows), which lives in the `locations` table of our own
   database — see server-python/app/locations.py and
   `python -m scripts.import_locations`.

   So these are thin wrappers over /api/locations. The server does the matching
   and ranking in SQL and returns at most `limit` rows, so a keystroke costs one
   small request and no DataForSEO call. */
import { api } from "./api";

/* Rows of one kind matching what the user typed, best match first.
   kind: "country" | "region" | "city"
   opts.country / opts.region: the choices made in the inputs ABOVE this one —
   passing them is what makes the three inputs cascade. */
export async function searchLocations(kind, query, { country, region, limit } = {}) {
  const params = new URLSearchParams({ kind, q: query ?? "" });
  if (country != null) params.set("country", country);
  if (region != null) params.set("region", region);
  if (limit != null) params.set("limit", limit);
  const data = await api(`/locations/search?${params}`);
  return data.locations;
}

/* Split a project's stored location_code back into the three inputs, so the
   edit form opens pre-filled. Returns { country, region, city } — each either a
   location row or null. */
export async function resolveLocation(code) {
  return api(`/locations/resolve?code=${encodeURIComponent(code)}`);
}

/* How much geo data is loaded ({ countries, regions, cities, imported }). The
   picker uses `imported` to explain an empty Region search: a fresh database is
   seeded with countries + verified metros only, until the import has been run. */
export async function locationsStatus() {
  return api("/locations/status");
}
