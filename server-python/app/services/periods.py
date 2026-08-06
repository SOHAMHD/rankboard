"""Turning a "YYYY-MM" period key into something a human reads.

This lived in snapshot_service, which was deleted along with the snapshot
feature — but backlink_service and report_document both need it, and neither has
anything to do with snapshots. Kept deliberately dependency-free so anything can
import it.
"""

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def label_for(period_key: str) -> str:
    """"2026-07" -> "July 2026". Returns the input unchanged if it isn't a period."""
    try:
        year, month = period_key.split("-")
        return f"{MONTH_NAMES[int(month) - 1]} {year}"
    except (ValueError, IndexError, AttributeError):
        return period_key


#: Old name, kept so nothing breaks on the rename.
_label_for = label_for
