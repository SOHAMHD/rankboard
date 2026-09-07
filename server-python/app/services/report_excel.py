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

#: GA4 metric id -> what to call it in a section heading.
#:
#: The country and landing-page tables are bare counts, and nothing on the sheet
#: said which count. A client looking at "/blog · 143" couldn't tell whether that
#: was active users, total users, sessions or views — and the two sections don't
#: have to report the same metric. The heading now names it, and it is derived
#: from the constants above so changing one changes the label with it.
_METRIC_LABELS = {
    "activeUsers": "Active Users",
    "totalUsers": "Total Users",
    "newUsers": "New Users",
    "sessions": "Sessions",
    "screenPageViews": "Page Views",
    "engagedSessions": "Engaged Sessions",
}


def _metric_label(metric):
    """Human name for a GA4 metric id, falling back to the id itself.

    An unmapped metric shows its raw id rather than silently omitting the label:
    an ugly heading is a prompt to add it here, a missing one is the bug this
    whole mapping exists to fix.
    """
    return _METRIC_LABELS.get(metric) or str(metric)

#: How the per-keyword ranks collapse into the single "Keywords Rank" figure.
#: "ranked_count" — how many tracked keywords hold a position at all.
#: "avg_position" — mean position of those that do.
KEYWORDS_RANK_MODE = "ranked_count"

COUNTRY_BLOCK = "ga4-by_country_city"
PAGE_BLOCK = "ga4-by_landing_page"

MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

_EMPTY = "—"

#: Heading for the row-number column, on every sheet. Spelt out rather than "#",
#: which reads as a code or an id in a sheet a client opens.
_INDEX_HEADING = "Sr no"

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
#: Section headings are bold, not coloured. Colour is reserved for the header
#: band at the top of each sheet — a tinted band plus zebra striping plus blue
#: heading text left the page competing with the figures on it.
_SECTION_FONT = Font(bold=True, name="Arial", color=_INK, size=10)
_BODY_FONT = Font(name="Arial", color=_INK, size=10)
_LABEL_FONT = Font(name="Arial", color=_INK, size=10, bold=True)
_MUTED_FONT = Font(name="Arial", color=_MUTED, size=10)

#: Rank movement on the Keywords sheet, applied to the figure itself rather than
#: as a cell fill — the sheet's only block of colour is the header band, and a
#: green wash behind every improved month would put that back.
_RANK_UP_FONT = Font(name="Arial", color="15803D", size=10, bold=True)    # green-700
_RANK_DOWN_FONT = Font(name="Arial", color="B91C1C", size=10, bold=True)  # red-700
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
_RANK_FMT = "0.0"

#: Duration formats. Both are written against an Excel time serial (see
#: _duration_cell), and both use bracketed elapsed codes — `[s]` / `[m]` — rather
#: than bare `s` / `m`. Bare `m` is ambiguous in a number format (Excel reads it
#: as "month" unless it can infer otherwise from neighbouring codes), and the
#: unbracketed forms roll over: 90 minutes would display as 30, having silently
#: carried an hour. Bracketed codes mean "total elapsed", which is what a
#: duration is.
_SEC_FMT = '[s]"s"'                 # 45  -> 45s
_MIN_FMT = '[m]"m" ss"s"'           # 84  -> 1m 24s

#: Seconds in a day. An Excel time is a fraction of one.
_DAY_SECONDS = 86400.0


def _duration_cell(seconds):
    """Render a second count as a duration: seconds under a minute, m + s above.

    GA4 gives engagement time as raw seconds, and the sheet used to print it that
    way whatever the size — "372s" left the reader doing the division. Showing
    decimal minutes instead was worse: "1.4m" reads as 1m 4s but means 1m 24s.

    So the cell holds a real Excel duration — the second count over 86400 — and
    the number format renders it. That keeps the value numeric and sortable, and
    lets Excel do the minutes-and-seconds arithmetic rather than this function
    formatting a string that only looks like a number.

    The unit choice can't live in the format alone: a format can branch on a
    value (`[<60]…;[>=60]…`) but not scale one, and both branches here need the
    same scaling. So the branch is here and the matching format comes back with
    the value.

    Returns (value, number_format). Non-numeric input passes straight through so
    the sentinel used for missing months keeps its own handling in _write.
    """
    if seconds is None or isinstance(seconds, bool) or not isinstance(seconds, (int, float)):
        return seconds, _SEC_FMT
    # Rounded before the comparison, not after: 59.9s rounds to 60, and deciding
    # on the raw value would have shown that as "60s".
    whole = round(seconds)
    fmt = _SEC_FMT if abs(whole) < 60 else _MIN_FMT
    return whole / _DAY_SECONDS, fmt


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


#: (label, resolver, number format).
#:
#: Every row is numbered in its own right. Paid/organic pairs used to share an
#: index, leaving the second of each pair with a blank number cell — so the sheet
#: skipped 4 and 6, and "Traffic from Organic Social" read as a footnote to the
#: paid row above it rather than a figure of its own.
_SCALAR_ROWS = (
    ("Total Users", lambda d: _overview(d, "totalUsers"), _INT_FMT),
    ("New/Unique Users", lambda d: _overview(d, "newUsers"), _INT_FMT),
    ("Direct User Traffic", lambda d: _channel(d, "Direct"), _INT_FMT),
    ("Traffic from Organic Search", lambda d: _channel(d, "Organic Search"), _INT_FMT),
    ("Traffic from Paid Search", lambda d: _channel(d, "Paid Search"), _INT_FMT),
    ("Traffic from Referrals", lambda d: _channel(d, "Referral"), _INT_FMT),
    ("Traffic from Paid Social", lambda d: _channel(d, "Paid Social"), _INT_FMT),
    ("Traffic from Organic Social", lambda d: _channel(d, "Organic Social"), _INT_FMT),
    ("Avg. Engagement Time", lambda d: _overview(d, "avgEngagementSeconds"), _SEC_FMT),
    ("Clicks", lambda d: _num(_gsc_totals(d).get("clicks")), _INT_FMT),
    ("Impression", lambda d: _num(_gsc_totals(d).get("impressions")), _INT_FMT),
    ("CTR", _ctr, _PCT_FMT),
    ("Bounce Rate", _bounce_rate, _PCT_FMT),
    ("Keywords Rank", _keywords_rank, _RANK_FMT if KEYWORDS_RANK_MODE == "avg_position" else _INT_FMT),
    ("Backlinks", _backlinks, _INT_FMT),
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

    The window is also one calendar year. A workbook covers the pinned report's
    year and nothing before it, so January 2027's export starts a fresh sheet
    rather than carrying twelve 2026 columns forward — a workbook that grew
    without bound would eventually be unreadable, and a client's 2027 report is
    not the place to restate 2026.
    """
    cutoff = pinned.get("periodKey")
    year = str(cutoff or "")[:4]
    best = {}
    for r in rows:
        key = r.get("periodKey")
        if key is None or (cutoff is not None and key > cutoff):
            continue
        # Same-year only. Compared on the period key's own "YYYY-MM" text, which
        # is how every other window in this module is decided.
        if year and not str(key).startswith(year):
            continue
        if key not in best or (r.get("id") or 0) > (best[key].get("id") or 0):
            best[key] = r
    best[cutoff] = pinned
    return [best[k] for k in sorted(best)]


def excel_filename(project, versions):
    # The company, not the contact.
    #
    # `clientName` is the person the work is for — "Richa" — while `name` is the
    # business, "Gaia Pharmacy". Preferring clientName here named the download
    # after whoever happened to be the contact, so several unrelated projects
    # sharing an account manager all exported as Richa_SEO_Report_Aug_2026.xlsx
    # and overwrote each other in the downloads folder. The PDF has always been
    # named from the project, so this also makes the two formats agree.
    company = (project.get("name") or project.get("clientName") or "report").strip()
    slug = "".join(c if c.isalnum() else "_" for c in company).strip("_") or "report"
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
    # Figures centre in their column. Right-aligning them lined the digits up
    # against the next month's column rule instead of sitting under the month
    # heading, which is what the eye tracks when reading along a row.
    cell.alignment = align or (_CENTRE if numeric or value == _EMPTY else _LEFT)
    return cell


def build_workbook(project, versions, keyword_order=None):
    """Three sheets: the month-by-month roll-up, Keywords, and Backlinks.

    One column per month on the first two, oldest first. Sections flow — nothing
    is at a fixed row.

    `keyword_order` is optional so existing callers keep working; without it the
    Keywords sheet falls back to the order the stored report sections present,
    which is by rank rather than the dashboard's.
    """
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

    for col, title in enumerate([_INDEX_HEADING, "Parameters"], start=1):
        _write(ws, 1, col, title, font=_HEADER_FONT, fill=_HEADER_FILL,
               align=_CENTRE if col == 1 else _LEFT, border=_HEADER_BORDER)
    for i, version in enumerate(versions):
        _write(ws, 1, 3 + i, _month_label(version.get("periodKey")), font=_HEADER_FONT,
               fill=_HEADER_FILL, align=_CENTRE, border=_HEADER_BORDER)
    ws.row_dimensions[1].height = 26

    row = 2
    index = 0
    for label, resolve, fmt in _SCALAR_ROWS:
        index += 1
        _write(ws, row, 1, index, align=_CENTRE)
        _write(ws, row, 2, label, font=_LABEL_FONT)
        for i, version in enumerate(versions):
            value = resolve(version.get("data"))
            cell_fmt = fmt
            if fmt is _SEC_FMT:
                # Duration rows pick their own unit per cell, so a month averaging
                # 45s and one averaging 6m each read naturally in the same row.
                value, cell_fmt = _duration_cell(value)
            _write(ws, row, 3 + i, _EMPTY if value is None else value, fmt=cell_fmt)
        ws.row_dimensions[row].height = 17
        row += 1

    def section(title, entities, block_id, section_key, metric):
        nonlocal row, index
        index += 1
        _write(ws, row, 1, index, font=_SECTION_FONT, align=_CENTRE)
        _write(ws, row, 2, title, font=_SECTION_FONT)
        for i in range(len(versions)):
            _write(ws, row, 3 + i, None)
        ws.row_dimensions[row].height = 20
        row += 1

        if not entities:
            _write(ws, row, 2, "No rows selected in the report.", font=_NOTE_FONT,
                   align=_LEFT_INDENT)
            for i in range(len(versions)):
                _write(ws, row, 3 + i, None)
            row += 1
            return

        for name in entities:
            _write(ws, row, 1, None)
            _write(ws, row, 2, name, align=_LEFT_INDENT)
            for i, version in enumerate(versions):
                value = _entity_value(version, block_id, section_key, metric, name)
                _write(ws, row, 3 + i, _EMPTY if value is None else value, fmt=_INT_FMT)
            ws.row_dimensions[row].height = 17
            row += 1

    # The parenthetical carries the metric, not a restatement of the title —
    # "Top Performing Pages (Top Performing Pages)" spent the only space
    # available for saying what the numbers actually are.
    section(f"Top Countries ({_metric_label(COUNTRY_METRIC)})", countries,
            COUNTRY_BLOCK, "by_country_city", COUNTRY_METRIC)
    section(f"Top Performing Pages ({_metric_label(PAGE_METRIC)})", pages,
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

    # Wide enough for the "Sr no" heading itself, not just the digits under it.
    ws.column_dimensions["A"].width = 7
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

    _keywords_sheet(wb, versions, keyword_order)
    _backlinks_sheet(wb, versions)

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _sheet_header(ws, label, months):
    """The shared chrome: numbered first column, a label column, then months.

    `months` empty means the sheet has no month columns at all — the backlinks
    list is one month's, so drawing Jun and Jul over it would imply data that
    doesn't exist.
    """
    ws.sheet_view.showGridLines = False
    for col, title in enumerate([_INDEX_HEADING, label], start=1):
        _write(ws, 1, col, title, font=_HEADER_FONT, fill=_HEADER_FILL,
               align=_CENTRE if col == 1 else _LEFT, border=_HEADER_BORDER)
    for i, month in enumerate(months):
        _write(ws, 1, 3 + i, month, font=_HEADER_FONT, fill=_HEADER_FILL,
               align=_CENTRE, border=_HEADER_BORDER)
    ws.row_dimensions[1].height = 26


def _sheet_layout(ws, label_width, month_count):
    # Wide enough for the "Sr no" heading itself, not just the digits under it.
    ws.column_dimensions["A"].width = 7
    ws.column_dimensions["B"].width = label_width
    for i in range(month_count):
        ws.column_dimensions[get_column_letter(3 + i)].width = 13
    ws.freeze_panes = "C2" if month_count else "A2"
    ws.print_title_rows = "1:1"
    ws.print_title_cols = "A:B"
    ws.page_setup.orientation = "portrait"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True


def _keyword_ranks(data):
    """term -> that month's position, for one version."""
    kw = ((data or {}).get("sections") or {}).get("keywords") or {}
    out = {}
    for item in kw.get("items") or []:
        term = (item.get("term") or "").strip()
        if term:
            out[term] = _num(item.get("current_rank"))
    return out


def _keyword_rows(versions, keyword_order):
    """Every term seen in the workbook's months, in the dashboard's order.

    The union matters: a keyword added in July still gets its August rank and an
    empty June, rather than vanishing from the sheet because it wasn't tracked all
    year.

    `keyword_order` is the project's terms as the Keywords screen lists them
    (created_at, id). It's passed in because the stored report sections are
    rank-sorted and their items carry no created_at, so that order can't be
    recovered from the report data. Terms not in the list — renamed or deleted
    since — follow in the order the months themselves present them, so nothing is
    dropped just because the live keyword list has moved on.
    """
    seen = []
    for version in versions:
        for term in _keyword_ranks(version.get("data")):
            if term not in seen:
                seen.append(term)
    if not keyword_order:
        return seen
    known = [t for t in keyword_order if t in seen]
    return known + [t for t in seen if t not in set(known)]


def _rank_font(current, previous, tracked_before):
    """Colour for one rank figure, judged against the month before it.

    Search rank counts down: position 3 beats position 12. So an improvement is a
    *smaller* number, which is the opposite of every other figure in this workbook
    and the reason this can't be a generic "went up / went down" helper.

    Returns None — meaning leave the figure in the ordinary body font — whenever
    there is nothing honest to compare against:

    * the first month in the workbook, which has no previous column;
    * a keyword that wasn't tracked the month before, so its "change" would be
      measured from nothing;
    * a month where the keyword holds no position at all (the cell is the greyed
      em-dash, and colouring a gap would imply a movement nobody can see);
    * an unchanged position, which is news only by being absent.

    A keyword that was tracked but unranked and now holds a position counts as an
    improvement: entering the results at all is the movement.
    """
    if current is None or not tracked_before:
        return None
    if previous is None:
        return _RANK_UP_FONT
    if current < previous:
        return _RANK_UP_FONT
    if current > previous:
        return _RANK_DOWN_FONT
    return None


def _keywords_sheet(wb, versions, keyword_order):
    ws = wb.create_sheet("Keywords")
    months = [_month_label(v.get("periodKey")) for v in versions]
    _sheet_header(ws, "Keyword", months)

    terms = _keyword_rows(versions, keyword_order)
    per_month = [_keyword_ranks(v.get("data")) for v in versions]

    row = 2
    if not terms:
        _write(ws, row, 2, "No keywords are tracked for this project.",
               font=_NOTE_FONT, align=_LEFT_INDENT)
        for i in range(len(months)):
            _write(ws, row, 3 + i, None)
    else:
        for n, term in enumerate(terms, start=1):
            _write(ws, row, 1, n, align=_CENTRE)
            _write(ws, row, 2, term)
            for i, ranks in enumerate(per_month):
                rank = ranks.get(term)
                # Compared against the column immediately to the left, which is
                # the previous month — `versions` is oldest-first. `term in prev`
                # rather than prev.get(term) is not None, so "tracked but
                # unranked" is distinguishable from "not tracked yet".
                prev = per_month[i - 1] if i else None
                font = _rank_font(rank, (prev or {}).get(term),
                                  tracked_before=bool(prev) and term in prev)
                # A tracked keyword holding no position is a gap, not a zero —
                # and not a 0 that would sort as the best rank on the sheet.
                _write(ws, row, 3 + i, _EMPTY if rank is None else rank,
                       fmt=_INT_FMT, font=font)
            ws.row_dimensions[row].height = 17
            row += 1
    _sheet_layout(ws, 46, len(months))


def _backlinks_sheet(wb, versions):
    """The report month's backlinks, and only that month's.

    No month columns. Each month's backlinks are an independent list — the data
    holds a URL and nothing else per link, so there is no figure to put under
    Jun or Jul, and repeating the same URL across columns would say only that it
    was imported twice.
    """
    ws = wb.create_sheet("Backlinks")
    _sheet_header(ws, "Backlink URL", [])

    newest = versions[-1] if versions else {}
    bl = (((newest.get("data") or {}).get("sections") or {}).get("backlinks")) or {}
    urls = [(i.get("url") or "").strip() for i in bl.get("items") or []]
    urls = [u for u in urls if u]
    count = _num(bl.get("count"))
    if count is None:
        count = len(urls)

    # Label and figure in one cell, in the URL column.
    #
    # The count used to sit in C, which put it in a column of its own with no
    # heading over it and nothing else beneath it — it read as a stray number
    # floating beside the list rather than the list's total. This sheet has no
    # month columns, so B is the only column that means anything here.
    _write(ws, 2, 1, None)
    _write(ws, 2, 2,
           f"Total backlinks · {_month_label(newest.get('periodKey'))} — {count:,}",
           font=_LABEL_FONT)
    ws.row_dimensions[2].height = 18

    row = 3
    if not urls:
        _write(ws, row, 2, "No backlinks recorded for this month.",
               font=_NOTE_FONT, align=_LEFT_INDENT)
    else:
        for n, url in enumerate(urls, start=1):
            _write(ws, row, 1, n, align=_CENTRE)
            _write(ws, row, 2, url)
            ws.row_dimensions[row].height = 17
            row += 1

    # Sized to the longest URL actually present rather than a fixed guess, so the
    # links sit inside the column instead of spilling across D, E, F. Capped
    # because a single tracking URL with a long query string would otherwise push
    # the column past anything printable.
    longest = max((len(u) for u in urls), default=0)
    _sheet_layout(ws, min(max(longest + 3, 48), 130), 0)
