"""The month-by-month Excel roll-up.

Rebuilt from the saved reports on every download rather than stored and appended
to. The visible result is the same — one new column each month, earlier columns
untouched — because a frozen report_version is immutable, so last month's column
is drawn from last month's report and cannot change. Rebuilding also means the
sheet can't drift out of step with the reports, and a download can be repeated.

Which countries and landing pages appear is the author's choice, taken from the
newest report's row selection (`included` on its data_table blocks) — the same
selection the PDF renders. Their per-month figures come from each month's own
report, so a country selected for the first time this month still gets its
history filled in.
"""

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .periods import MONTH_NAMES

#: Which GA4 metric the country and landing-page sections report. Both sections
#: carry several; these two are what "traffic" means everywhere else in the
#: report, so the sheet stays comparable with the PDF.
COUNTRY_METRIC = "activeUsers"
PAGE_METRIC = "activeUsers"

#: How the per-keyword ranks collapse into the single "Keywords Rank" figure.
#: "ranked_count" — how many tracked keywords hold a position at all.
#: "avg_position" — mean position of those that do.
KEYWORDS_RANK_MODE = "ranked_count"

COUNTRY_BLOCK = "ga4-by_country_city"
PAGE_BLOCK = "ga4-by_landing_page"

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_EMPTY = "—"

#: Built around the app's own primary, Tailwind blue-600, so a client opening the
#: workbook sees the same blue as the dashboard it came from.
_BLUE = "2563EB"        # blue-600  — header band
_BLUE_DARK = "1E40AF"   # blue-800  — section heading text
_BLUE_TINT = "DBEAFE"   # blue-100  — section heading band
_BLUE_FAINT = "EFF6FF"  # blue-50   — zebra banding
_GRID = "CBD5E1"        # slate-300 — cell borders, visible on white
_MUTED = "94A3B8"       # slate-400 — the em-dash, so a gap reads as a gap
_INK = "1E293B"         # slate-800 — body text

_HEADER_FILL = PatternFill("solid", start_color=_BLUE)
_SECTION_FILL = PatternFill("solid", start_color=_BLUE_TINT)
_BAND_FILL = PatternFill("solid", start_color=_BLUE_FAINT)

_HEADER_FONT = Font(bold=True, color="FFFFFF", name="Arial", size=11)
_SECTION_FONT = Font(bold=True, name="Arial", color=_BLUE_DARK, size=10)
_BODY_FONT = Font(name="Arial", color=_INK, size=10)
_LABEL_FONT = Font(name="Arial", color=_INK, size=10, bold=True)
_MUTED_FONT = Font(name="Arial", color=_MUTED, size=10)
_NOTE_FONT = Font(name="Arial", color=_MUTED, size=9, italic=True)

_HAIR = Side(style="thin", color=_GRID)
_BORDER = Border(left=_HAIR, right=_HAIR, top=_HAIR, bottom=_HAIR)
#: A heavier rule under the header band, so the month columns read as a table
#: rather than as more rows.
_HEADER_BORDER = Border(
    left=Side(style="thin", color=_BLUE),
    right=Side(style="thin", color=_BLUE),
    top=Side(style="thin", color=_BLUE),
    bottom=Side(style="medium", color=_BLUE_DARK),
)

_LEFT = Alignment(horizontal="left", vertical="center")
_LEFT_INDENT = Alignment(horizontal="left", vertical="center", indent=1)
_RIGHT = Alignment(horizontal="right", vertical="center")
_CENTRE = Alignment(horizontal="center", vertical="center")

_INT_FMT = "#,##0"
_PCT_FMT = "0.00%"
_SEC_FMT = '0"s"'
_RANK_FMT = "0.0"


def _num(v):
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    return v


def _ga4(data, which="report_month"):
    ga4 = ((data or {}).get("sections") or {}).get("ga4") or {}
    return (ga4.get(which) or {}).get("sections") or {}


def _totals(data, key):
    return (_ga4(data).get(key) or {}).get("totals") or {}


def _rows(data, key):
    return (_ga4(data).get(key) or {}).get("rows") or []


def _gsc_totals(data):
    gsc = ((data or {}).get("sections") or {}).get("gsc") or {}
    return (gsc.get("report_month") or {}).get("totals") or {}


def _overview(data, metric):
    return _num(_totals(data, "users_overview").get(metric))


def _channel(data, name):
    """Users for one GA4 channel group. Channels are rows, not keys."""
    target = name.strip().lower()
    for r in _rows(data, "by_channel"):
        dims = r.get("dims") or []
        if dims and str(dims[0]).strip().lower() == target:
            return _num((r.get("metrics") or {}).get("totalUsers"))
    return None


def _bounce_rate(data):
    """GA4 stops reporting bounce rate directly; it is the inverse of engagement.

    Derived here rather than in report_google._derive so that reports frozen
    before this feature existed still produce the row.
    """
    totals = _totals(data, "users_overview")
    engaged, sessions = _num(totals.get("engagedSessions")), _num(totals.get("sessions"))
    if engaged is None or not sessions:
        return None
    return 1 - (engaged / sessions)


def _ctr(data):
    ctr = _num(_gsc_totals(data).get("ctr"))
    if ctr is None:
        return None
    # GSC hands back a 0-1 fraction; a few historical blobs hold whole percents.
    return ctr / 100 if ctr > 1 else ctr


def _keywords_rank(data):
    kw = ((data or {}).get("sections") or {}).get("keywords") or {}
    ranks = [_num(i.get("current_rank")) for i in kw.get("items") or []]
    ranks = [r for r in ranks if r is not None]
    if not ranks:
        return None
    if KEYWORDS_RANK_MODE == "avg_position":
        return round(sum(ranks) / len(ranks), 1)
    return len(ranks)


def _backlinks(data):
    bl = ((data or {}).get("sections") or {}).get("backlinks") or {}
    return _num(bl.get("count"))


#: (number, label, resolver, number format). A number of None marks a row that
#: continues the one above it, which is why the sample sheet skips 4 and 6 —
#: paid/organic pairs share an index.
_SCALAR_ROWS = (
    (1, "Total Users", lambda d: _overview(d, "totalUsers"), _INT_FMT),
    (2, "New/Unique Users", lambda d: _overview(d, "newUsers"), _INT_FMT),
    (3, "Direct User Traffic", lambda d: _channel(d, "Direct"), _INT_FMT),
    (4, "Traffic from Organic Search", lambda d: _channel(d, "Organic Search"), _INT_FMT),
    (None, "Traffic from Paid Search", lambda d: _channel(d, "Paid Search"), _INT_FMT),
    (5, "Traffic from Referrals", lambda d: _channel(d, "Referral"), _INT_FMT),
    (6, "Traffic from Paid Social", lambda d: _channel(d, "Paid Social"), _INT_FMT),
    (None, "Traffic from Organic Social", lambda d: _channel(d, "Organic Social"), _INT_FMT),
    (7, "Avg. Engagement Time", lambda d: _overview(d, "avgEngagementSeconds"), _SEC_FMT),
    (8, "Clicks", lambda d: _num(_gsc_totals(d).get("clicks")), _INT_FMT),
    (9, "Impression", lambda d: _num(_gsc_totals(d).get("impressions")), _INT_FMT),
    (10, "CTR", _ctr, _PCT_FMT),
    (11, "Bounce Rate", _bounce_rate, _PCT_FMT),
    (12, "Keywords Rank", _keywords_rank, _RANK_FMT if KEYWORDS_RANK_MODE == "avg_position" else _INT_FMT),
    (13, "Backlinks", _backlinks, _INT_FMT),
)


def _blocks(content):
    if not content or content.get("type") != "report_document":
        return []
    return content.get("blocks") or []


def _block(content, block_id):
    for b in _blocks(content):
        if b.get("id") == block_id:
            return b
    return None


def _included_entities(content, block_id, dim_key="dim0"):
    """The author's chosen rows, in the order they arranged them.

    Deliberately not re-sorted by value: the editor's order is a decision, and
    the sample sheet keeps it (its biggest country sits second).
    """
    block = _block(content, block_id)
    if block is None:
        return []
    out, seen = [], set()
    for row in block.get("rows") or []:
        if row.get("included") is False:
            continue
        name = ((row.get("cells") or {}).get(dim_key) or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append(name)
    return out


def _entity_value(version, block_id, section_key, metric, name):
    """One entity's figure for one month.

    Prefers that month's own document, so a figure an author corrected by hand is
    the figure the sheet shows. Falls back to the raw GA4 rows, which is what
    fills in the history of an entity only selected later.

    `included` is ignored here on purpose. Leaving a country out of March's PDF
    says nothing about its March traffic, and the series should not show a hole.
    """
    target = name.strip().lower()

    block = _block(version.get("content"), block_id)
    if block is not None:
        for row in block.get("rows") or []:
            cells = row.get("cells") or {}
            if (cells.get("dim0") or "").strip().lower() == target:
                value = _num(cells.get(metric))
                if value is not None:
                    return value

    # Country rows are country x region x city, so one country spans many rows.
    total = None
    for row in _rows(version.get("data"), section_key):
        dims = row.get("dims") or []
        if dims and str(dims[0]).strip().lower() == target:
            value = _num((row.get("metrics") or {}).get(metric))
            if value is not None:
                total = value if total is None else total + value
    return total


def _month_label(period_key):
    try:
        year, month = str(period_key).split("-")
        return f"{datetime(int(year), int(month), 1):%b}-{year}"
    except (ValueError, IndexError, AttributeError):
        return str(period_key)


def columns_for(rows, pinned):
    """The month columns for one report, oldest first.

    `pinned` is the report being exported, and it wins its own month outright —
    even against a newer draft for the same period. The export has to describe the
    version the author is looking at, the way the PDF does; picking "newest per
    month" instead meant a click on one report could export another report's row
    selection.

    Later months are dropped: an August report has no September column.
    """
    cutoff = pinned.get("periodKey")
    best = {}
    for r in rows:
        key = r.get("periodKey")
        if key is None or (cutoff is not None and key > cutoff):
            continue
        if key not in best or (r.get("id") or 0) > (best[key].get("id") or 0):
            best[key] = r
    best[cutoff] = pinned
    return [best[k] for k in sorted(best)]


def excel_filename(project, versions):
    client = (project.get("clientName") or project.get("name") or "report").strip()
    slug = "".join(c if c.isalnum() else "_" for c in client).strip("_") or "report"
    period = versions[-1].get("periodKey") if versions else ""
    try:
        year, month = str(period).split("-")
        stamp = f"{MONTH_NAMES[int(month) - 1]}_{year}"
    except (ValueError, IndexError, AttributeError):
        stamp = str(period) or "report"
    return f"{slug}_SEO_Report_{stamp}.xlsx"


#: Excel treats a cell opening with any of these as a formula, not as text. Page
#: paths and country names come from Google, but an author can retype a dimension
#: cell by hand in the report editor — and this workbook is emailed to the client,
#: who is the one who opens it. Never let a label become executable.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _write(ws, row, col, value, *, fmt=None, font=None, fill=None,
           align=None, border=None):
    cell = ws.cell(row=row, column=col)
    cell.value = value
    if isinstance(value, str) and value.startswith(_FORMULA_LEAD):
        # Forced back to a string after assignment: openpyxl has already inferred
        # "formula" from the leading character by this point. The displayed text is
        # unchanged — this only stops Excel from evaluating it.
        cell.data_type = "s"
    numeric = isinstance(value, (int, float)) and not isinstance(value, bool)
    # The em-dash is greyed rather than styled like a figure, so a month with no
    # data for a row is visibly a gap and not a value someone might read.
    cell.font = font or (_MUTED_FONT if value == _EMPTY else _BODY_FONT)
    cell.border = border or _BORDER
    if fill is not None:
        cell.fill = fill
    if fmt and numeric:
        cell.number_format = fmt
    cell.alignment = align or (_RIGHT if numeric else _CENTRE if value == _EMPTY else _LEFT)
    return cell


def build_workbook(project, versions):
    """One column per month, oldest first. Sections flow — nothing is at a fixed row."""
    if not versions:
        raise ValueError("This project has no saved reports yet, so there is nothing to export.")

    newest = versions[-1]
    countries = _included_entities(newest.get("content"), COUNTRY_BLOCK)
    pages = _included_entities(newest.get("content"), PAGE_BLOCK)

    wb = Workbook()
    ws = wb.active
    ws.title = "SEO Report"
    # Every cell that carries data draws its own border, so Excel's own gridlines
    # only add noise between them.
    ws.sheet_view.showGridLines = False

    width = 2 + len(versions)

    for col, title in enumerate(["#", "Parameters"], start=1):
        _write(ws, 1, col, title, font=_HEADER_FONT, fill=_HEADER_FILL,
               align=_CENTRE if col == 1 else _LEFT, border=_HEADER_BORDER)
    for i, version in enumerate(versions):
        _write(ws, 1, 3 + i, _month_label(version.get("periodKey")), font=_HEADER_FONT,
               fill=_HEADER_FILL, align=_CENTRE, border=_HEADER_BORDER)
    ws.row_dimensions[1].height = 26

    row = 2
    index = 0
    for number, label, resolve, fmt in _SCALAR_ROWS:
        if number is not None:
            index = number
        _write(ws, row, 1, index if number is not None else None, align=_CENTRE)
        _write(ws, row, 2, label, font=_LABEL_FONT)
        for i, version in enumerate(versions):
            value = resolve(version.get("data"))
            _write(ws, row, 3 + i, _EMPTY if value is None else value, fmt=fmt)
        ws.row_dimensions[row].height = 17
        row += 1

    def section(title, entities, block_id, section_key, metric):
        nonlocal row, index
        index += 1
        _write(ws, row, 1, index, font=_SECTION_FONT, fill=_SECTION_FILL, align=_CENTRE)
        _write(ws, row, 2, title, font=_SECTION_FONT, fill=_SECTION_FILL)
        for i in range(len(versions)):
            _write(ws, row, 3 + i, None, fill=_SECTION_FILL)
        ws.row_dimensions[row].height = 20
        row += 1

        if not entities:
            _write(ws, row, 2, "No rows selected in the report.", font=_NOTE_FONT,
                   align=_LEFT_INDENT)
            for i in range(len(versions)):
                _write(ws, row, 3 + i, None)
            row += 1
            return

        # Banded, because these two sections are the long ones — a client tracking
        # one page across four month columns is reading along a row.
        for n, name in enumerate(entities):
            band = _BAND_FILL if n % 2 else None
            _write(ws, row, 1, None, fill=band)
            _write(ws, row, 2, name, fill=band, align=_LEFT_INDENT)
            for i, version in enumerate(versions):
                value = _entity_value(version, block_id, section_key, metric, name)
                _write(ws, row, 3 + i, _EMPTY if value is None else value,
                       fmt=_INT_FMT, fill=band)
            ws.row_dimensions[row].height = 17
            row += 1

    section("Traffic from Countries (Top Countries)", countries,
            COUNTRY_BLOCK, "by_country_city", COUNTRY_METRIC)
    section("Top Performing Pages (Top Performing Pages)", pages,
            PAGE_BLOCK, "by_landing_page", PAGE_METRIC)

    # There used to be a "Data gaps" footer here listing why a month's GA4 or GSC
    # fetch failed. It printed sources.<provider>.reason verbatim, and those
    # strings are raw Google client errors — the full request URI, the response
    # body, the service-account principal. This workbook is emailed to the client,
    # which made it the only place that detail reached anyone outside the team.
    #
    # A failed month already reads as a gap: every cell in its column renders the
    # greyed em-dash rather than a zero. The reason itself stays where it is
    # useful and safe — the report view in the dashboard, which is gated to
    # author roles.

    ws.column_dimensions["A"].width = 4.5
    ws.column_dimensions["B"].width = 46
    for i in range(len(versions)):
        ws.column_dimensions[get_column_letter(3 + i)].width = 13
    ws.freeze_panes = "C2"
    # Printing: the label column repeats on every page and the sheet is scaled to
    # one page wide, so a long page list doesn't split its months across sheets.
    ws.print_title_rows = "1:1"
    ws.print_title_cols = "A:B"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
