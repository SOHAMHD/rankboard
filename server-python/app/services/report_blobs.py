from . import report_registry as registry

_MISSING = object()

_GROUP = {
    registry.SOURCE_GA4: "GA4",
    registry.SOURCE_GSC: "GSC",
    registry.SOURCE_MOZ: "Moz",
}

_GA4_TOTALS = ["sections", "ga4", "report_month", "sections", "users_overview", "totals"]
_GA4_DELTAS = ["sections", "ga4", "deltas"]
_GSC_TOTALS = ["sections", "gsc", "report_month", "totals"]
_GSC_DELTAS = ["sections", "gsc", "deltas"]
_MOZ = ["sections", "moz"]
_MOZ_DELTAS = ["sections", "moz", "deltas"]

BLOB_MAP = {
    "moz.domain_authority": (_MOZ + ["domain_authority"], _MOZ_DELTAS + ["domain_authority"]),
    "moz.linking_domains":  (_MOZ + ["linking_domains"],  _MOZ_DELTAS + ["linking_domains"]),
    "moz.inbound_links":    (_MOZ + ["inbound_links"],    _MOZ_DELTAS + ["inbound_links"]),
    "ga4.sessions":             (_GA4_TOTALS + ["sessions"],             None),
    "ga4.total_users":          (_GA4_TOTALS + ["totalUsers"],           _GA4_DELTAS + ["totalUsers"]),
    "ga4.avg_session_duration": (_GA4_TOTALS + ["avgEngagementSeconds"], _GA4_DELTAS + ["avgEngagementSeconds"]),
    "gsc.clicks":       (_GSC_TOTALS + ["clicks"],      _GSC_DELTAS + ["clicks"]),
    "gsc.impressions":  (_GSC_TOTALS + ["impressions"], _GSC_DELTAS + ["impressions"]),
    "gsc.ctr":          (_GSC_TOTALS + ["ctr"],         _GSC_DELTAS + ["ctr"]),
    "gsc.avg_position": (_GSC_TOTALS + ["position"],    _GSC_DELTAS + ["position"]),
}


def _dig(obj, path):
    cur = obj
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return _MISSING
        cur = cur[key]
    return cur


def resolve_scalar_blobs(data: dict | None) -> list[dict]:
    if not data:
        return []
    fields_by_name = {f["name"]: f for f in registry.REPORT_FIELDS}
    out: list[dict] = []
    for name, (value_path, delta_path) in BLOB_MAP.items():
        field = fields_by_name.get(name)
        if field is None:
            continue
        value = _dig(data, value_path)
        if value is _MISSING:
            continue
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
