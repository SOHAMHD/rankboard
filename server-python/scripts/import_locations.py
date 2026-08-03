"""IMPORT LOCATIONS — load DataForSEO's full geo list into OUR database.

Run it once (and again whenever you want to refresh), from server-python/:

    python -m scripts.import_locations                  # live: needs DataForSEO creds
    python -m scripts.import_locations --country in     # one country only (ISO code)
    python -m scripts.import_locations --file geo.json  # from a saved API response
    python -m scripts.import_locations --dry-run        # fetch + classify, write nothing

WHY: the project picker's three inputs (Country / Region / City) type-ahead
against our own `locations` table, so a keystroke is a local indexed query —
never a DataForSEO call. DataForSEO stays the source of the `location_code`
values, because that integer is exactly what the rank checker sends back to them.

WHAT IT DOES
  1. GET {DATAFORSEO_BASE}/v3/serp/google/locations  (Basic auth, ~100k rows,
     one request. Free: DataForSEO doesn't charge for this reference endpoint.)
     NOTE the path — it is NOT under /organic/. The locations list belongs to
     the SERP API as a whole, so /v3/serp/google/organic/locations returns
     task error 40402 "Invalid Path".
  2. Classifies every row into country / region / city and resolves each one's
     country + region ancestor by walking `location_code_parent`.
  3. Replaces the `locations` table contents in a single transaction, so the API
     is never left looking at a half-loaded table.

Existing projects are untouched: a project stores DataForSEO location codes, and
this only ever refreshes the lookup rows those codes point at.
"""
import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

# Allow `python -m scripts.import_locations` AND `python scripts/import_locations.py`
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402  (path set up above)
from app.config import DATAFORSEO_BASE, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD  # noqa: E402

ENDPOINT = "/v3/serp/google/locations"  # append /{iso} to filter to one country

# Anything below a city — useful to nobody in a project picker, and it triples
# the row count. Dropped unless --keep-all is passed.
NOISE_TYPES = {"Airport", "University", "Postal Code", "Neighborhood", "Borough"}

# Types that are a city (or city-like) even when they sit directly under a
# country, which happens in small countries and city-states.
CITY_TYPES = {
    "City", "Town", "Village", "Municipality", "City Region", "Metro Area",
    "Locality", "Postal Town", "Airport", "University", "Postal Code",
    "Neighborhood", "Borough",
}


def fetch_live(country: str | None = None) -> list[dict]:
    """One authenticated GET. DataForSEO returns every location it supports for
    Google SERPs, each row carrying its own code, name, type and parent.

    `country` is an optional ISO code ("in", "au") that filters the list
    server-side — handy for a quick run, but the picker is worldwide, so the
    unfiltered call is the normal one."""
    if not DATAFORSEO_LOGIN or not DATAFORSEO_PASSWORD:
        sys.exit(
            "DATAFORSEO_LOGIN / DATAFORSEO_PASSWORD are not set (server-python/.env).\n"
            "These are the DataForSEO API credentials — NOT a Google account.\n"
            "Or pass --file with a saved response."
        )
    token = base64.b64encode(f"{DATAFORSEO_LOGIN}:{DATAFORSEO_PASSWORD}".encode()).decode()
    url = DATAFORSEO_BASE.rstrip("/") + ENDPOINT + (f"/{country.strip().lower()}" if country else "")
    print(f"GET {url} …")
    req = urllib.request.Request(url, headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=180) as resp:  # noqa: S310 (fixed host)
        payload = json.load(resp)
    return _unwrap(payload)


def _unwrap(payload: dict) -> list[dict]:
    """Pull the item list out of DataForSEO's tasks->result envelope, and fail
    loudly with their own status message rather than a KeyError."""
    if payload.get("status_code") not in (20000, None):
        sys.exit(f"DataForSEO error {payload.get('status_code')}: {payload.get('status_message')}")
    for task in payload.get("tasks") or []:
        if task.get("status_code") not in (20000, None):
            hint = ""
            if task.get("status_code") == 40402:  # Invalid Path
                hint = (
                    f"\nThe locations endpoint is {ENDPOINT} — NOT under /organic/."
                    " Check DATAFORSEO_BASE in .env too."
                )
            sys.exit(f"DataForSEO task error {task.get('status_code')}: {task.get('status_message')}{hint}")
        result = task.get("result")
        if result:
            return result
    sys.exit("No locations in the response — nothing to import.")


def classify(items: list[dict], keep_all: bool = False) -> list[tuple]:
    """Turn DataForSEO's flat list into our rows.

    Each item looks like:
      {"location_code": 1000676, "location_name": "Perth,Western Australia,Australia",
       "location_code_parent": 21160, "country_iso_code": "AU", "location_type": "City"}

    kind: 'country' for location_type Country; 'city' for the city-like types or
    anything more than one level below a country; 'region' for the state/province
    layer directly under a country. So the picker's second input holds exactly
    what DataForSEO nests a city inside, whatever that country calls it.
    """
    by_code = {int(i["location_code"]): i for i in items if i.get("location_code") is not None}

    def chain(code: int) -> list[dict]:
        """The row plus its ancestors, closest first. Depth-capped so a cyclic
        parent reference in the source data can't hang the import."""
        out, seen = [], set()
        while code is not None and code in by_code and code not in seen and len(out) < 12:
            seen.add(code)
            item = by_code[code]
            out.append(item)
            parent = item.get("location_code_parent")
            code = int(parent) if parent is not None else None
        return out

    rows, skipped = [], 0
    for code, item in by_code.items():
        ltype = (item.get("location_type") or "").strip()
        if not keep_all and ltype in NOISE_TYPES:
            skipped += 1
            continue

        ancestors = chain(code)
        full_name = (item.get("location_name") or "").strip()
        name = full_name.split(",")[0].strip() or full_name
        country = next((a for a in ancestors if (a.get("location_type") or "") == "Country"), None)
        country_code = int(country["location_code"]) if country else None
        # Everything between this row and its country, closest first.
        above = [a for a in ancestors[1:] if a is not country]

        if ltype == "Country":
            kind, country_code, region_code = "country", code, None
        elif ltype in CITY_TYPES or len(above) >= 1:
            kind = "city"
            # The region a city sits in = its highest ancestor below the country.
            region_code = int(above[-1]["location_code"]) if above else None
        else:
            kind, region_code = "region", None

        rows.append((
            code, name, full_name, kind, country_code, region_code,
            (item.get("country_iso_code") or "").strip() or None, ltype or None, "",
        ))

    if skipped:
        print(f"Skipped {skipped:,} sub-city rows ({', '.join(sorted(NOISE_TYPES))}) — pass --keep-all to include them")
    return rows


def write(rows: list[tuple], merge: bool = False) -> None:
    """Write the rows in ONE transaction, so a reader sees either the whole old
    set or the whole new one — never a half-loaded table.

    Default (a full worldwide fetch) replaces everything. `merge=True` — used by
    --country — deletes only the codes it is about to re-insert, leaving every
    other country intact."""
    conn = db.get_connection()
    try:
        conn.execute("BEGIN")
        if merge:
            conn.executemany("DELETE FROM locations WHERE location_code = ?", [(r[0],) for r in rows])
        else:
            conn.execute("DELETE FROM locations")
        conn.executemany(
            "INSERT INTO locations (location_code, name, full_name, kind,"
            " country_code, region_code, country_iso, location_type, alt)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        # Keep the hand-written search aliases ("UK", "USA", "UAE") the seed
        # added — DataForSEO has no equivalent field, and the import wiped them.
        from app.locations import COUNTRY_SEED

        conn.executemany(
            "UPDATE locations SET alt = ? WHERE location_code = ? AND kind = 'country'",
            [(c["alt"], c["locationCode"]) for c in COUNTRY_SEED if c.get("alt")],
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description="Import DataForSEO locations into our database.")
    ap.add_argument("--file", help="Read a saved DataForSEO locations response instead of calling the API")
    ap.add_argument("--country", help="ISO code to limit the fetch to one country, e.g. in, au, us")
    ap.add_argument("--dry-run", action="store_true", help="Report what would be imported; write nothing")
    ap.add_argument("--keep-all", action="store_true", help="Also import airports, universities, postal codes, neighborhoods")
    args = ap.parse_args()

    # Creates the table on a database that predates it (idempotent).
    db.init_db()

    if args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else _unwrap(payload)
        print(f"Loaded {len(items):,} rows from {args.file}")
    else:
        items = fetch_live(args.country)
        print(f"Fetched {len(items):,} rows")

    # A --country run must NOT wipe the other countries already loaded, so a
    # filtered import merges instead of replacing.
    merge = bool(args.country)

    rows = classify(items, keep_all=args.keep_all)
    counts = {k: sum(1 for r in rows if r[3] == k) for k in ("country", "region", "city")}
    print(f"Classified: {counts['country']:,} countries · {counts['region']:,} regions · {counts['city']:,} cities")

    if args.dry_run:
        print("--dry-run: nothing written.")
        return

    write(rows, merge=merge)
    print(f"Imported {len(rows):,} locations into {'Postgres' if db.IS_POSTGRES else db.DB_PATH}")


if __name__ == "__main__":
    main()
