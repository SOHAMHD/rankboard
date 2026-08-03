import json
from pathlib import Path

_DIR = Path(__file__).resolve().parent

COUNTRY_SEED = json.loads((_DIR / "countries.json").read_text(encoding="utf-8"))["countries"]

LOCATIONS = json.loads((_DIR / "locations.json").read_text(encoding="utf-8"))

VALID_LOCATION_CODES = {c["locationCode"] for c in LOCATIONS["countries"]} | {
    city["locationCode"]
    for c in LOCATIONS["countries"]
    for city in c["cities"]
}

_CODE_BY_ISO = {c["iso"]: c["locationCode"] for c in COUNTRY_SEED}


def search_keys(name: str, full_name: str, alt: str) -> tuple[str, str]:
    words = f"{full_name} {alt}".replace(",", " ").lower().split()
    return name.lower(), " " + " ".join(words) + " "


def seed_rows() -> list[tuple]:
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
                continue
            full = f"{city['name']}, {country_name}"
            rows[code] = (
                code, city["name"], full, "city",
                country_code, None, iso, "City", "",
                *search_keys(city["name"], full, ""),
            )

    return list(rows.values())
