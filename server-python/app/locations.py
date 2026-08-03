"""LOCATION SEED — the offline starting point for the country / region / city
picker.

WHERE THE REAL DATA LIVES: the `locations` table in our own database (see
db.py). It holds every country, region and city DataForSEO supports, keyed by
the DataForSEO `location_code` the rank checker sends. Fill/refresh it with

    python -m scripts.import_locations          # from server-python/

which pulls DataForSEO's full locations list once and writes it to our DB. The
API then never calls DataForSEO to answer a type-ahead — it queries our table.

WHAT THIS FILE IS FOR: the boot-time seed, so a fresh database has a usable
picker before that import has ever been run.

  • countries.json — all 249 ISO-3166 countries. A DataForSEO country
    location_code is simply 2000 + the ISO-3166 numeric code (India 356 -> 2356,
    Australia 036 -> 2036, UK 826 -> 2826), so this list is exact and needs no
    API call. `alt` holds extra strings the search should match but never
    displays ("UK", "USA", "UAE").

  • locations.json — the original hand-verified metro cities for the countries
    we serve today. Kept so city search works out of the box; the import
    replaces it with the full worldwide set (regions included).

Nothing validates against these constants any more — the server validates a
submitted code against the `locations` TABLE, so codes added by the import are
accepted too.
"""
import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent

# ── Countries: all of them (see the module docstring for the 2000+ISO rule) ───
COUNTRY_SEED = json.loads((_DIR / "countries.json").read_text(encoding="utf-8"))["countries"]

# ── Cities: the original verified metro seed ─────────────────────────────────
LOCATIONS = json.loads((_DIR / "locations.json").read_text(encoding="utf-8"))

# Legacy: the codes the old two-dropdown picker allowed. No longer the trust
# boundary (the DB table is), kept because it documents the verified metro set.
VALID_LOCATION_CODES = {c["locationCode"] for c in LOCATIONS["countries"]} | {
    city["locationCode"]
    for c in LOCATIONS["countries"]
    for city in c["cities"]
}

# ISO -> country location_code, so the city seed can be attached to the full
# country list even for a country locations.json spells differently.
_CODE_BY_ISO = {c["iso"]: c["locationCode"] for c in COUNTRY_SEED}


def search_keys(name: str, full_name: str, alt: str) -> tuple[str, str]:
    """The two derived columns the type-ahead actually queries:

      name_key    lower(name), so the indexed prefix match needs no LOWER().
      search_key  " perth western australia australia " — full_name with commas
                  turned into spaces, plus alt, lowercased, padded with a space
                  at each end. One column to LIKE against instead of three ORs,
                  and the padding makes '% perth%' mean "a word starts with
                  perth". db.py's _backfill_location_keys() builds the identical
                  strings in SQL for rows imported before these existed.
    """
    words = f"{full_name} {alt}".replace(",", " ").lower().split()
    return name.lower(), " " + " ".join(words) + " "


def seed_rows() -> list[tuple]:
    """Every seed row as a `locations` tuple:
        (location_code, name, full_name, kind, country_code, region_code,
         country_iso, location_type, alt, name_key, search_key)

    Countries from countries.json, cities from locations.json. No regions —
    region codes are not derivable offline, so the Region search stays empty
    until `python -m scripts.import_locations` has been run. Codes are unique
    (locations.location_code is the primary key), country rows win on collision.
    """
    rows: dict[int, tuple] = {}

    for c in COUNTRY_SEED:
        alt = c.get("alt", "")
        rows[c["locationCode"]] = (
            c["locationCode"], c["name"], c["name"], "country",
            c["locationCode"], None, c["iso"], "Country", alt,
            *search_keys(c["name"], c["name"], alt),
        )

    for c in LOCATIONS["countries"]:
        iso = c["iso"]
        country_code = _CODE_BY_ISO.get(iso, c["locationCode"])
        country_name = next(
            (cs["name"] for cs in COUNTRY_SEED if cs["iso"] == iso), c["name"]
        )
        for city in c["cities"]:
            code = city["locationCode"]
            if code in rows:
                continue  # never shadow a country row
            full = f"{city['name']}, {country_name}"
            rows[code] = (
                code, city["name"], full, "city",
                country_code, None, iso, "City", "",
                *search_keys(city["name"], full, ""),
            )

    return list(rows.values())
