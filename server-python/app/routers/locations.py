"""LOCATION ROUTES — the type-ahead behind the project picker's three inputs.

Country / Region / City are free-text inputs, not dropdowns: the user types a few
letters and we return the matching rows from OUR `locations` table (populated by
`python -m scripts.import_locations`). Nothing here calls DataForSEO — a keystroke
is a local indexed query.

Cascading: pass the chosen country to narrow regions and cities, and the chosen
region to narrow cities further. Region and city are optional; the project's
effective DataForSEO target is the most specific of the three.
"""
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_db
from ..security import require_active_user

router = APIRouter(dependencies=[Depends(require_active_user)])

KINDS = ("country", "region", "city")


def row_to_location(r: sqlite3.Row) -> dict:
    return {
        "code": r["location_code"],
        "name": r["name"],
        "fullName": r["full_name"],
        "kind": r["kind"],
        "countryCode": r["country_code"],
        "regionCode": r["region_code"],
        "countryIso": r["country_iso"],
    }


@router.get("/search")
def search_locations(
    kind: str = Query(..., description="country | region | city"),
    q: str = Query("", description="What the user has typed so far"),
    country: int | None = Query(None, description="Chosen country location_code — narrows regions and cities"),
    region: int | None = Query(None, description="Chosen region location_code — narrows cities"),
    limit: int = Query(20, ge=1, le=50),
    db: sqlite3.Connection = Depends(get_db),
):
    """Rows of one `kind` whose name matches `q`, best match first.

    Ranking is done in SQL so we only ever ship `limit` rows:
      0. the name starts with what was typed  ("del" -> Delhi)
      1. a word inside the name starts with it ("york" -> New York)
      2. anything else that contains it, incl. the alias column ("UK", "USA")
    then shortest name, then alphabetical — so the exact/obvious hit is on top.

    An empty `q` is valid and returns the first `limit` rows alphabetically for
    the current filter, which is what makes clicking an empty input feel like a
    dropdown.
    """
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(KINDS)}.")

    needle = q.strip().lower()
    starts, word, contains = f"{needle}%", f"% {needle}%", f"%{needle}%"

    where = ["kind = ?"]
    params: list = [kind]

    # Cascade. A region/city search with no country chosen searches worldwide,
    # which is deliberate: typing "perth" before picking a country still works.
    if kind in ("region", "city") and country is not None:
        where.append("country_code = ?")
        params.append(country)
    if kind == "city" and region is not None:
        where.append("region_code = ?")
        params.append(region)
    if needle:
        where.append("(LOWER(name) LIKE ? OR LOWER(full_name) LIKE ? OR LOWER(alt) LIKE ?)")
        params += [contains, contains, contains]

    if needle:
        # Shortest name breaks ties, so "Delhi" beats "New Delhi" for "del".
        order = (
            "CASE WHEN LOWER(name) LIKE ? THEN 0 WHEN LOWER(name) LIKE ? THEN 1 ELSE 2 END,"
            " LENGTH(name), name"
        )
        order_params = [starts, word]
    else:
        order, order_params = "name", []  # nothing typed yet: plain A-Z

    # Placeholder order follows the SQL text: WHERE first, then ORDER BY, then LIMIT.
    rows = db.execute(
        "SELECT location_code, name, full_name, kind, country_code, region_code, country_iso"
        f" FROM locations WHERE {' AND '.join(where)}"
        f" ORDER BY {order} LIMIT ?",
        (*params, *order_params, limit),
    ).fetchall()

    return {"locations": [row_to_location(r) for r in rows]}


@router.get("/resolve")
def resolve_location(
    code: int = Query(..., description="A stored project location_code"),
    db: sqlite3.Connection = Depends(get_db),
):
    """Split one stored code back into the three inputs, so the edit form opens
    pre-filled. Returns country/region/city, each null when it doesn't apply."""
    row = db.execute(
        "SELECT location_code, name, full_name, kind, country_code, region_code, country_iso"
        " FROM locations WHERE location_code = ?",
        (code,),
    ).fetchone()
    if row is None:
        # A legacy or unsupported code: still show the number rather than
        # silently blanking the user's saved target.
        return {"country": None, "region": None, "city": None, "unknownCode": code}

    def one(c: int | None) -> dict | None:
        if c is None:
            return None
        r = db.execute(
            "SELECT location_code, name, full_name, kind, country_code, region_code, country_iso"
            " FROM locations WHERE location_code = ?",
            (c,),
        ).fetchone()
        return row_to_location(r) if r else None

    kind = row["kind"]
    return {
        "country": one(row["country_code"]),
        "region": one(row["region_code"]) if kind == "city" else (row_to_location(row) if kind == "region" else None),
        "city": row_to_location(row) if kind == "city" else None,
    }


@router.get("/status")
def locations_status(db: sqlite3.Connection = Depends(get_db)):
    """How much geo data is loaded. The picker uses this to tell the user to run
    the import when the region layer is still empty (the boot seed has countries
    and metro cities only)."""
    rows = db.execute("SELECT kind, COUNT(*) AS n FROM locations GROUP BY kind").fetchall()
    counts = {r["kind"]: r["n"] for r in rows}
    return {
        "countries": counts.get("country", 0),
        "regions": counts.get("region", 0),
        "cities": counts.get("city", 0),
        "imported": counts.get("region", 0) > 0,
    }
