"""REPORT FIELD REGISTRY — the single source of truth for "what a report needs
and where it comes from".

Every datum a generated report can carry is declared here ONCE: a stable name,
its SOURCE (which table/column, or 'deferred' for a not-yet-wired feed), and its
TYPE (the formatting category the content editor's format menu will later use).
Adding a new field to a report is a one-line addition to REPORT_FIELDS — nothing
else in the pipeline hard-codes a field list.

Sources wired today:
  • ranks    — per-keyword rank, frozen from snapshot_ranks for the chosen snapshot
  • moz      — domain_authority / linking_domains / inbound_links from moz_metrics
  • keywords — the keyword list + current-vs-previous comparison (keywords + snapshot)
  • ga4      — fetched LIVE from the GA4 Data API at generate time, then FROZEN
  • gsc      — fetched LIVE from Search Console at generate time, then FROZEN

GA4/GSC were previously source='deferred' (registered but not fetched). As of the
GA4/GSC slice they are REAL sources (source='ga4'/'gsc'), fetched at generate time
(see report_google.py) and frozen into report_version.data_json. Their absence now
FAILS validation, exactly like ranks/Moz. There are no deferred fields left.
"""

# ── Format types (the editor's future format menu draws from these) ──────────
TYPE_COUNT = "count"        # a whole number (DA score, link counts, sessions…)
TYPE_DURATION = "duration"  # a length of time (avg session duration…)
TYPE_PERCENT = "percent"    # a ratio shown as a percentage (CTR…)
TYPE_RANK = "rank"          # a SERP position (lower is better)
TYPE_TEXT = "text"          # free text (keyword terms…)

FIELD_TYPES = frozenset({TYPE_COUNT, TYPE_DURATION, TYPE_PERCENT, TYPE_RANK, TYPE_TEXT})

# ── Sources ──────────────────────────────────────────────────────────────────
SOURCE_SNAPSHOT_RANKS = "snapshot_ranks"  # frozen ranks for the chosen snapshot
SOURCE_MOZ = "moz_metrics"                # the period's Moz row
SOURCE_KEYWORDS = "keywords"              # keyword list / current-vs-previous
SOURCE_GA4 = "ga4"                        # live GA4 Data API fetch, frozen at generate
SOURCE_GSC = "gsc"                        # live Search Console fetch, frozen at generate
SOURCE_DEFERRED = "deferred"              # registered but not yet sourced (none currently)


# Each entry: name (stable id), source, type, deferred flag, human label.
# `deferred` is a convenience mirror of `source == SOURCE_DEFERRED`, set
# explicitly so a reader never has to infer it.
REPORT_FIELDS = (
    # ── ranks (frozen snapshot) ──────────────────────────────────────────────
    {"name": "ranks.keyword_rank", "source": SOURCE_SNAPSHOT_RANKS,
     "column": "rank", "type": TYPE_RANK, "deferred": False,
     "label": "Keyword rank (frozen snapshot)"},

    # ── moz ──────────────────────────────────────────────────────────────────
    {"name": "moz.domain_authority", "source": SOURCE_MOZ,
     "column": "domain_authority", "type": TYPE_COUNT, "deferred": False,
     "label": "Domain Authority"},
    {"name": "moz.linking_domains", "source": SOURCE_MOZ,
     "column": "linking_domains", "type": TYPE_COUNT, "deferred": False,
     "label": "Linking domains"},
    {"name": "moz.inbound_links", "source": SOURCE_MOZ,
     "column": "inbound_links", "type": TYPE_COUNT, "deferred": False,
     "label": "Inbound links (backlinks)"},

    # ── keywords (current vs previous) ───────────────────────────────────────
    {"name": "keywords.current_rank", "source": SOURCE_KEYWORDS,
     "column": "current_rank", "type": TYPE_RANK, "deferred": False,
     "label": "Current rank"},
    {"name": "keywords.previous_rank", "source": SOURCE_KEYWORDS,
     "column": "previous_rank", "type": TYPE_RANK, "deferred": False,
     "label": "Previous rank"},

    # ── GA4 — LIVE-FETCHED at generate time, then frozen ─────────────────────
    {"name": "ga4.sessions", "source": SOURCE_GA4,
     "column": None, "type": TYPE_COUNT, "deferred": False,
     "label": "Sessions"},
    {"name": "ga4.total_users", "source": SOURCE_GA4,
     "column": None, "type": TYPE_COUNT, "deferred": False,
     "label": "Total users"},
    {"name": "ga4.avg_session_duration", "source": SOURCE_GA4,
     "column": None, "type": TYPE_DURATION, "deferred": False,
     "label": "Avg. session duration"},

    # ── GSC — LIVE-FETCHED at generate time, then frozen ─────────────────────
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
    """Fields the pipeline actually sources from the DB this slice."""
    return [f for f in REPORT_FIELDS if not f["deferred"]]


def deferred_fields() -> list[dict]:
    """Registered-but-not-yet-sourced fields (GA4/GSC). Present so the structure
    is ready; NOT fetched and NOT validated in this slice."""
    return [f for f in REPORT_FIELDS if f["deferred"]]


def required_sources() -> set[str]:
    """The non-deferred data sources that validation insists be PRESENT for a
    freeze. Derived from the registry, so it's automatically right as fields are
    added. (snapshot_ranks + keywords both come from the chosen snapshot; moz
    from moz_metrics.)"""
    return {f["source"] for f in active_fields()}


def manifest() -> dict:
    """A compact registry snapshot embedded into every frozen report blob, so a
    later editor slice can read the field set / types / deferred markers WITHOUT
    importing this module against a possibly-changed registry."""
    return {
        "field_types": sorted(FIELD_TYPES),
        "fields": [
            {"name": f["name"], "source": f["source"], "type": f["type"],
             "deferred": f["deferred"], "label": f["label"]}
            for f in REPORT_FIELDS
        ],
        "deferred_fields": [f["name"] for f in deferred_fields()],
    }
