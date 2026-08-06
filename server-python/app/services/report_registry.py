
TYPE_COUNT = "count"
TYPE_DURATION = "duration"
TYPE_PERCENT = "percent"
TYPE_RANK = "rank"
TYPE_TEXT = "text"

FIELD_TYPES = frozenset({TYPE_COUNT, TYPE_DURATION, TYPE_PERCENT, TYPE_RANK, TYPE_TEXT})

SOURCE_MOZ = "moz_metrics"
SOURCE_KEYWORDS = "keywords"
SOURCE_GA4 = "ga4"
SOURCE_GSC = "gsc"
SOURCE_DEFERRED = "deferred"


#: Fields offered to the report editor's "/" insert menu, via manifest().
#:
#: Every entry here must have a matching path in report_blobs.BLOB_MAP, or it
#: appears in the menu and then resolves to nothing. Three used to break that
#: rule — ranks.keyword_rank (from the removed snapshot storage) and
#: keywords.current_rank / previous_rank (from the removed legacy columns). All
#: three were per-keyword values with nowhere sensible to point in a per-report
#: scalar map; keyword ranks belong in the Keyword Rankings table, which is
#: built directly from the keywords section.
REPORT_FIELDS = (
    {"name": "moz.domain_authority", "source": SOURCE_MOZ,
     "column": "domain_authority", "type": TYPE_COUNT, "deferred": False,
     "label": "Domain Authority"},
    {"name": "moz.linking_domains", "source": SOURCE_MOZ,
     "column": "linking_domains", "type": TYPE_COUNT, "deferred": False,
     "label": "Linking domains"},
    {"name": "moz.inbound_links", "source": SOURCE_MOZ,
     "column": "inbound_links", "type": TYPE_COUNT, "deferred": False,
     "label": "Inbound links (backlinks)"},

    {"name": "ga4.sessions", "source": SOURCE_GA4,
     "column": None, "type": TYPE_COUNT, "deferred": False,
     "label": "Sessions"},
    {"name": "ga4.total_users", "source": SOURCE_GA4,
     "column": None, "type": TYPE_COUNT, "deferred": False,
     "label": "Total users"},
    # Name kept for backwards compatibility with saved report documents, but the
    # value is avgEngagementSeconds — engagement time per active user, NOT session
    # duration. Those are different GA4 metrics: session duration includes idle
    # time and reads far higher. The label is corrected so nobody compares it
    # against GA4's "Average session duration" and concludes the app is wrong.
    {"name": "ga4.avg_session_duration", "source": SOURCE_GA4,
     "column": None, "type": TYPE_DURATION, "deferred": False,
     "label": "Avg. engagement time / user"},

    {"name": "gsc.clicks", "source": SOURCE_GSC,
     "column": None, "type": TYPE_COUNT, "deferred": False,
     "label": "Clicks"},
    {"name": "gsc.impressions", "source": SOURCE_GSC,
     "column": None, "type": TYPE_COUNT, "deferred": False,
     "label": "Impressions"},
    {"name": "gsc.ctr", "source": SOURCE_GSC,
     "column": None, "type": TYPE_PERCENT, "deferred": False,
     "label": "CTR"},
    {"name": "gsc.avg_position", "source": SOURCE_GSC,
     "column": None, "type": TYPE_RANK, "deferred": False,
     "label": "Avg. position"},
)


def active_fields() -> list[dict]:
    return [f for f in REPORT_FIELDS if not f["deferred"]]


def deferred_fields() -> list[dict]:
    return [f for f in REPORT_FIELDS if f["deferred"]]


def required_sources() -> set[str]:
    return {f["source"] for f in active_fields()}


def manifest() -> dict:
    return {
        "field_types": sorted(FIELD_TYPES),
        "fields": [
            {"name": f["name"], "source": f["source"], "type": f["type"],
             "deferred": f["deferred"], "label": f["label"]}
            for f in REPORT_FIELDS
        ],
        "deferred_fields": [f["name"] for f in deferred_fields()],
    }
