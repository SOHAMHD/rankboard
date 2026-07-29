/* Country + metro-city seed for the rank-check location picker.

   SINGLE SOURCE OF TRUTH: the list lives with the server, at
   server-python/app/locations.json, so the API can validate a submitted
   locationCode against it (the client is never trusted). We bundle that SAME
   file into the client build here — no /api round-trip for a small static list
   that rarely changes. Because both sides read one physical file, they cannot
   drift. (Vite serves this cross-directory import in dev via server.fs.allow
   in vite.config.js; the build inlines it, so dist has no runtime dependency.) */
import seed from "../../server-python/app/locations.json";

export const COUNTRIES = seed.countries;
