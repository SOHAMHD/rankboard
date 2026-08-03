import argparse
import base64
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import db  # noqa: E402  (path set up above)
from app.config import DATAFORSEO_BASE, DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD  # noqa: E402

ENDPOINT = "/v3/serp/google/locations"

NOISE_TYPES = {"Airport", "University", "Postal Code", "Neighborhood", "Borough"}

CITY_TYPES = {
    "City", "Town", "Village", "Municipality", "City Region", "Metro Area",
    "Locality", "Postal Town", "Airport", "University", "Postal Code",
    "Neighborhood", "Borough",
}


def fetch_live(country: str | None = None) -> list[dict]:
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
    if payload.get("status_code") not in (20000, None):
        sys.exit(f"DataForSEO error {payload.get('status_code')}: {payload.get('status_message')}")
    for task in payload.get("tasks") or []:
        if task.get("status_code") not in (20000, None):
            hint = ""
            if task.get("status_code") == 40402:
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
    by_code = {int(i["location_code"]): i for i in items if i.get("location_code") is not None}

    def chain(code: int) -> list[dict]:
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
        above = [a for a in ancestors[1:] if a is not country]

        if ltype == "Country":
            kind, country_code, region_code = "country", code, None
        elif ltype in CITY_TYPES or len(above) >= 1:
            kind = "city"
            region_code = int(above[-1]["location_code"]) if above else None
        else:
            kind, region_code = "region", None

        rows.append((
            code, name, full_name, kind, country_code, region_code,
            (item.get("country_iso_code") or "").strip() or None, ltype or None, "",
            *search_keys(name, full_name, ""),
        ))

    if skipped:
        print(f"Skipped {skipped:,} sub-city rows ({', '.join(sorted(NOISE_TYPES))}) — pass --keep-all to include them")
    return rows


def write(rows: list[tuple], merge: bool = False) -> None:
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

    db.init_db()

    if args.file:
        payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
        items = payload if isinstance(payload, list) else _unwrap(payload)
        print(f"Loaded {len(items):,} rows from {args.file}")
    else:
        items = fetch_live(args.country)
        print(f"Fetched {len(items):,} rows")

    merge = bool(args.country)

    rows = classify(items, keep_all=args.keep_all)
    counts = {k: sum(1 for r in rows if r[3] == k) for k in ("country", "region", "city")}
    print(f"Classified: {counts['country']:,} countries · {counts['region']:,} regions · {counts['city']:,} cities")

    if args.dry_run:
        print("--dry-run: nothing written.")
        return

    write(rows, merge=merge)
    print(f"Imported {len(rows):,} locations into Postgres")


if __name__ == "__main__":
    main()
