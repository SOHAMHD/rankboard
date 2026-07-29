"""LOCATION SEED — the single source of truth for the country + metro-city
picker (locations.json, right beside this file).

The server loads it once at import and validates every submitted locationCode
against it (never trusting the client). The React client bundles the SAME
JSON file at build time (see client/src/locations.js), so there is no
/api round-trip and the two sides read one physical file — they cannot drift.

To add a country or city, edit locations.json only; nothing else changes."""
import json
from pathlib import Path

_PATH = Path(__file__).resolve().parent / "locations.json"
LOCATIONS = json.loads(_PATH.read_text(encoding="utf-8"))

# Every code a project may legally store: each country PLUS each of its metro
# cities. NULL (server default) is always allowed and never appears here.
VALID_LOCATION_CODES = {c["locationCode"] for c in LOCATIONS["countries"]} | {
    city["locationCode"]
    for c in LOCATIONS["countries"]
    for city in c["cities"]
}
