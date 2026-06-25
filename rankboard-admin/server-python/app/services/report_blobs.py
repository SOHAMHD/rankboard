"""REPORT BLOB RESOLVER — flattens a frozen report blob into the SCALAR "blobs"
the content editor can insert.

WHY THIS EXISTS (the 0(a) finding): the frozen `data_json` is NOT directly
resolvable from a stable blob name. Scalar values live at wildly different
depths and under different key spellings than the registry field names:

  registry name              frozen location
  ─────────────────────────  ──────────────────────────────────────────────────
  moz.domain_authority       sections.moz.domain_authority
  ga4.total_users            sections.ga4.report_month.sections.users_overview.totals.totalUsers
  ga4.avg_session_duration   sections.ga4.report_month.sections.users_overview.totals.avgEngagementSeconds
  gsc.avg_position           sections.gsc.report_month.totals.position

So this module owns the ONE mapping from each registry SCALAR field to its
(value path, delta path) inside the blob, and `resolve_scalar_blobs()` turns a
frozen blob into a flat list of:

  { name, label, type, source, group, currentValue, deltaValue }

This is the SINGLE source both the editor's palette and its live preview consume
(the frontend never digs into data_json itself). Reads FROZEN data only — no
live fetch. TABULAR fields (the keyword list, channel/country/landing-page
collections) are intentionally excluded: this slice only inserts scalars.
"""
from . import report_registry as registry

# Sentinel: a path segment was absent (vs. a real None/0 value, both of which
# are valid frozen data). A blob whose VALUE path is missing isn't "available".
_MISSING = object()

# Friendly group label per source, for palette grouping.
_GROUP = {
    registry.SOURCE_GA4: "GA4",
    registry.SOURCE_GSC: "GSC",
    registry.SOURCE_MOZ: "Moz",
}

# Shared path prefixes into the frozen blob.
_GA4_TOTALS = ["sections", "ga4", "report_month", "sections", "users_overview", "totals"]
_GA4_DELTAS = ["sections", "ga4", "deltas"]
_GSC_TOTALS = ["sections", "gsc", "report_month", "totals"]
_GSC_DELTAS = ["sections", "gsc", "deltas"]
_MOZ = ["sections", "moz"]
_MOZ_DELTAS = ["sections", "moz", "deltas"]

# The ONE mapping: registry SCALAR field name -> (value path, delta path | None).
# delta path is None where the frozen blob carries no delta for that field
# (e.g. ga4.sessions: ga4.deltas has activeUsers/newUsers/totalUsers/
# returningUsers/avgEngagementSeconds, but NOT sessions).
BLOB_MAP = {
    # Moz (flat scalars + deltas)
    "moz.domain_authority": (_MOZ + ["domain_authority"], _MOZ_DELTAS + ["domain_authority"]),
    "moz.linking_domains":  (_MOZ + ["linking_domains"],  _MOZ_DELTAS + ["linking_domains"]),
    "moz.inbound_links":    (_MOZ + ["inbound_links"],    _MOZ_DELTAS + ["inbound_links"]),
    # GA4 overview totals (registry name -> blob totals key)
    "ga4.sessions":             (_GA4_TOTALS + ["sessions"],             None),
    "ga4.total_users":          (_GA4_TOTALS + ["totalUsers"],           _GA4_DELTAS + ["totalUsers"]),
    "ga4.avg_session_duration": (_GA4_TOTALS + ["avgEngagementSeconds"], _GA4_DELTAS + ["avgEngagementSeconds"]),
    # GSC totals (registry name -> blob totals key)
    "gsc.clicks":       (_GSC_TOTALS + ["clicks"],      _GSC_DELTAS + ["clicks"]),
    "gsc.impressions":  (_GSC_TOTALS + ["impressions"], _GSC_DELTAS + ["impressions"]),
    "gsc.ctr":          (_GSC_TOTALS + ["ctr"],         _GSC_DELTAS + ["ctr"]),
    "gsc.avg_position": (_GSC_TOTALS + ["position"],    _GSC_DELTAS + ["position"]),
}


def _dig(obj, path):
    """Walk `path` (a list of dict keys) into `obj`. Returns the value (which may
    legitimately be None or 0) or `_MISSING` if any segment is absent."""
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def resolve_scalar_blobs(data: dict | None) -> list[dict]:
    """Flatten a frozen report blob (`data_json` parsed) into the list of available
    scalar blobs. A blob is "available" only when its VALUE path exists in the
    frozen data (so a section that wasn't frozen simply doesn't appear). A real 0
    is a valid value and IS included; only a truly absent path is skipped.

    Returns [] for empty/missing data. Each entry:
      { name, label, type, source, group, currentValue, deltaValue }
    deltaValue is None when the field has no frozen delta."""
    if not data:
        return []
    # Key off ALL declared fields (not just active_fields()): this resolver reads
    # FROZEN data, so a field already present in the blob must keep resolving even
    # if a later registry change re-defers its live source. BLOB_MAP is the gate
    # for what's a scalar chip; the registry just supplies label/type.
    fields_by_name = {f["name"]: f for f in registry.REPORT_FIELDS}
    out: list[dict] = []
    for name, (value_path, delta_path) in BLOB_MAP.items():
        field = fields_by_name.get(name)
        if field is None:
            continue  # registry no longer declares it (defensive)
        value = _dig(data, value_path)
        if value is _MISSING:
            continue  # section/value not present in this frozen blob
        delta = _dig(data, delta_path) if delta_path else _MISSING
        out.append({
            "name": name,
            "label": field["label"],
            "type": field["type"],
            "source": field["source"],
            "group": _GROUP.get(field["source"], field["source"]),
            "currentValue": value,
            "deltaValue": None if delta is _MISSING else delta,
        })
    return out
