import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..db import get_db
from ..security import require_active_user

router = APIRouter(dependencies=[Depends(require_active_user)])

KINDS = ("country", "region", "city")
COLS = "location_code, name, full_name, kind, country_code, region_code, country_iso, alt"
MAX_TOKENS = 4


def row_to_location(r: sqlite3.Row) -> dict:
    return {
        "code": r["location_code"],
        "name": r["name"],
        "fullName": r["full_name"],
        "kind": r["kind"],
        "countryCode": r["country_code"],
        "regionCode": r["region_code"],
        "countryIso": r["country_iso"],
        "alt": r["alt"] or "",
    }


def _scope(kind: str, country: int | None, region: int | None) -> tuple[list[str], list]:
    where, params = ["kind = ?"], [kind]
    if kind in ("region", "city") and country is not None:
        where.append("country_code = ?")
        params.append(country)
    if kind == "city" and region is not None:
        where.append("region_code = ?")
        params.append(region)
    return where, params


@router.get("/search")
def search_locations(
    kind: str = Query(..., description="country | region | city"),
    q: str = Query("", description="What the user has typed so far"),
    country: int | None = Query(None, description="Chosen country location_code, narrows regions and cities"),
    region: int | None = Query(None, description="Chosen region location_code, narrows cities"),
    limit: int = Query(20, ge=1, le=5000),
    db: sqlite3.Connection = Depends(get_db),
):
    if kind not in KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(KINDS)}.")

    needle = " ".join(q.lower().split())
    base_where, base_params = _scope(kind, country, region)

    if not needle:
        rows = db.execute(
            f"SELECT {COLS} FROM locations WHERE {' AND '.join(base_where)}"
            " ORDER BY name_key LIMIT ?",
            (*base_params, limit),
        ).fetchall()
        return {"locations": [row_to_location(r) for r in rows]}

    found = db.execute(
        f"SELECT {COLS} FROM locations WHERE {' AND '.join(base_where)}"
        " AND name_key LIKE ? ORDER BY LENGTH(name), name_key LIMIT ?",
        (*base_params, f"{needle}%", limit),
    ).fetchall()

    if len(found) < limit:
        seen = {r["location_code"] for r in found}
        tokens = needle.split()[:MAX_TOKENS]
        where = base_where + ["search_key LIKE ?"] * len(tokens)
        params = [*base_params, *(f"%{t}%" for t in tokens)]
        rest = db.execute(
            f"SELECT {COLS} FROM locations WHERE {' AND '.join(where)}"
            " ORDER BY CASE WHEN search_key LIKE ? THEN 0 ELSE 1 END,"
            " LENGTH(name), name_key LIMIT ?",
            (*params, f"% {needle}%", limit),
        ).fetchall()
        found = found + [r for r in rest if r["location_code"] not in seen][: limit - len(found)]

    return {"locations": [row_to_location(r) for r in found]}


@router.get("/resolve")
def resolve_location(
    code: int = Query(..., description="A stored project location_code"),
    db: sqlite3.Connection = Depends(get_db),
):
    rows = {
        r["location_code"]: r
        for r in db.execute(
            f"SELECT {COLS} FROM locations WHERE location_code = ?"
            " OR location_code = (SELECT country_code FROM locations WHERE location_code = ?)"
            " OR location_code = (SELECT region_code FROM locations WHERE location_code = ?)",
            (code, code, code),
        ).fetchall()
    }
    row = rows.get(code)
    if row is None:
        return {"country": None, "region": None, "city": None, "unknownCode": code}

    def one(c: int | None) -> dict | None:
        r = rows.get(c)
        return row_to_location(r) if r else None

    kind = row["kind"]
    return {
        "country": one(row["country_code"]),
        "region": one(row["region_code"]) if kind == "city" else (row_to_location(row) if kind == "region" else None),
        "city": row_to_location(row) if kind == "city" else None,
    }


@router.get("/status")
def locations_status(db: sqlite3.Connection = Depends(get_db)):
    rows = db.execute("SELECT kind, COUNT(*) AS n FROM locations GROUP BY kind").fetchall()
    counts = {r["kind"]: r["n"] for r in rows}
    return {
        "countries": counts.get("country", 0),
        "regions": counts.get("region", 0),
        "cities": counts.get("city", 0),
        "imported": counts.get("region", 0) > 0,
    }
