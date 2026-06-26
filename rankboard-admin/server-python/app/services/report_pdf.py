"""REPORT PDF — HTML→PDF render of a generated report version (headless Chrome).

FULL TEMPLATE SLICE: renders the COMPLETE multi-page monthly SEO report — cover,
table of contents, progress summary + key-metrics, achievements, Moz authority,
the GA4 audience grid + eight GA4 data tables, the GSC performance grid + daily
trend chart, the keyword-rankings table (green/red change cells), the numbered
backlinks list, and the targets / strategy narrative pages — with Poppins
embedded, the brand palette, a running footer on every page and page numbering.
It EXTENDS the proof slice: the working Playwright render_pdf() is reused as-is.

INPUT: the report_version block document (content_json, type "report_document")
plus its frozen data_json — exactly what report_service.get_version(include_data=
True) returns ({"content": ..., "data": ...}). Values are taken from the already-
seeded content blocks; nothing is re-fetched and nothing is stored.

ENGINE: Playwright + Chromium. The endpoint that calls render_pdf() is a SYNC
FastAPI handler, so FastAPI runs it in a worker thread (no asyncio loop) and the
Playwright SYNC API is safe to use.

ASSETS (server-python/app/assets/, embedded as base64 data URIs so set_content
has no external file deps):
  • "2rd Logo In HD Format PNG.png" — the fixed InfyApp agency logo (cover + top
    bars). Brand colours sampled from it: blue #0066a8, charcoal #424242.
  • Poppins-{Regular,Medium,SemiBold,Bold,Light}.ttf — embedded via @font-face.

PAGINATION: the template PRE-PAGINATES — long sections (GA4 tables, the keyword
table, the backlinks list) are split into fixed-size page chunks in Python, so
every emitted ``.page`` is exactly one physical A4 page. That gives deterministic,
correctly-numbered pages and a clean table of contents without relying on the
browser's flow breaks. @page is margin:0 (full-bleed cover); each page paints its
own footer band.

Missing/ungathered sections (available is False) render a clean "not available
for this period" panel — never a blank page or a broken layout.
"""
import base64
import html
import re
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

# ── Brand palette (sampled from the agency logo + report styling) ──────────────
_BLUE = "#0066a8"          # InfyApp brand blue (the logo "f")
_BLUE_DARK = "#004e7c"     # headings / accents
_BLUE_DEEP = "#013a5b"     # cover gradient end
_BLUE_TINT = "#e7f1f8"     # table header / soft fills
_BLUE_TINT2 = "#f3f8fc"    # zebra stripe
_CHARCOAL = "#424242"      # logo charcoal
_INK = "#2a2f36"           # body text
_MUTED = "#6b7280"         # secondary text
_BORDER = "#e2e8f0"        # hairlines
_BG_SOFT = "#f6f8fa"
_GREEN = "#157a3c"         # improvement
_GREEN_BG = "#e6f5ec"
_RED = "#c02a2a"           # decline
_RED_BG = "#fdeceb"

# How many rows/items fit on one physical page for each long section.
_TABLE_ROWS_PER_PAGE = 20
_KEYWORD_ROWS_PER_PAGE = 22
_BACKLINKS_PER_PAGE = 30


# ── asset embedding (cached; read once per process) ───────────────────────────
@lru_cache(maxsize=None)
def _data_uri(filename: str, mime: str) -> str:
    raw = (_ASSETS / filename).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


@lru_cache(maxsize=1)
def _logo_uri() -> str:
    return _data_uri("2rd Logo In HD Format PNG.png", "image/png")


@lru_cache(maxsize=1)
def _font_face_css() -> str:
    """@font-face rules embedding the Poppins weights actually used."""
    weights = [
        ("Poppins-Light.ttf", 300),
        ("Poppins-Regular.ttf", 400),
        ("Poppins-Medium.ttf", 500),
        ("Poppins-SemiBold.ttf", 600),
        ("Poppins-Bold.ttf", 700),
    ]
    faces = []
    for fname, weight in weights:
        uri = _data_uri(fname, "font/ttf")
        faces.append(
            "@font-face{font-family:'Poppins';font-style:normal;"
            f"font-weight:{weight};src:url({uri}) format('truetype');}}"
        )
    return "".join(faces)


# ── value / delta formatting (mirrors client lib/blobFormats.js defaults) ─────
def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _fmt_value(type_: str, v) -> str:
    """Default per-type display (matches blobFormats default format ids). PERCENT
    values are stored as FRACTIONS (0–1) so they're ×100 for display."""
    if not _num(v):
        return "—"
    try:
        if type_ == "count":
            return f"{round(v):,}"
        if type_ == "duration":
            return f"{round(v)}s"
        if type_ == "percent":
            return f"{round(v * 100, 2)}%"
        if type_ == "rank":
            return f"#{round(v)}"
        return html.escape(str(v))
    except Exception:
        return html.escape(str(v))


def _fmt_delta(type_: str, d):
    """(text, tone) for a delta. RANK is lower-is-better (negative = improvement);
    everything else: positive = growth. tone ∈ {up, down, flat} drives the color.
    The convention is intentional: ranks are stored current−previous, so a
    NEGATIVE rank delta means the position number dropped → improved → green."""
    if not _num(d) or d == 0:
        return ("—", "flat")
    improved = (d < 0) if type_ == "rank" else (d > 0)
    tone = "up" if improved else "down"
    s = "+" if d > 0 else ""  # negatives already carry "-"
    if type_ == "count":
        text = f"{s}{round(d):,}"
    elif type_ == "duration":
        text = f"{s}{round(d, 1)}s"
    elif type_ == "percent":
        text = f"{s}{round(d * 100, 2)}%"
    elif type_ == "rank":
        text = ("▲ " if improved else "▼ ") + str(abs(round(d, 1)))
    else:
        text = html.escape(str(d))
    return (text, tone)


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _chunk(seq, n):
    seq = seq or []
    return [seq[i:i + n] for i in range(0, len(seq), n)] or [[]]


# ── block pickers ─────────────────────────────────────────────────────────────
def _blocks(content: dict) -> list:
    if not content or content.get("type") != "report_document":
        return []
    return content.get("blocks") or []


def _find(content: dict, block_id: str) -> dict:
    for b in _blocks(content):
        if b.get("id") == block_id:
            return b
    return {}


def _header_block(content: dict) -> dict:
    for b in _blocks(content):
        if b.get("type") == "report_header":
            return b
    return {}


# ── shared fragments ──────────────────────────────────────────────────────────
def _unavailable(reason: str) -> str:
    return (f'<div class="unavailable"><span class="ua-icon">—</span>'
            f'<span>{_esc(reason or "Not available for this period.")}</span></div>')


def _section_head(title: str, sub: str = "") -> str:
    sub_html = f'<p class="sub">{_esc(sub)}</p>' if sub else ""
    return f'<h2 class="section"><span class="bar"></span>{_esc(title)}</h2>{sub_html}'


# ── metric grid ───────────────────────────────────────────────────────────────
def _metric_card(m: dict) -> str:
    type_ = m.get("type", "count")
    label = _esc(m.get("label"))
    cur = _fmt_value(type_, m.get("currentValue"))
    prev = _fmt_value(type_, m.get("previousValue"))
    dtext, tone = _fmt_delta(type_, m.get("deltaValue"))
    return f"""
      <div class="card">
        <div class="card-label">{label}</div>
        <div class="card-value">{cur}</div>
        <div class="card-row">
          <span class="prev">prev {prev}</span>
          <span class="delta {tone}">{_esc(dtext)}</span>
        </div>
      </div>"""


def _metric_grid_page(grid: dict, sub: str) -> str:
    title = (grid or {}).get("title") or "Key Metrics"
    head = _section_head(title, sub)
    if not grid or grid.get("available") is False:
        return head + _unavailable((grid or {}).get("unavailableReason"))
    cards = "".join(_metric_card(m) for m in (grid.get("metrics") or []))
    return head + f'<div class="grid">{cards}</div>'


# ── narrative ─────────────────────────────────────────────────────────────────
def _narrative_page(block: dict, banner: str = "") -> str:
    head = _section_head(block.get("title") or "Notes")
    paras = "".join(f"<p class='para'>{_esc(p)}</p>" for p in (block.get("paragraphs") or []))
    bullets = block.get("bullets") or []
    bl = ""
    if bullets:
        items = "".join(f"<li>{_esc(b)}</li>" for b in bullets)
        bl = f"<ul class='bullets'>{items}</ul>"
    if not paras and not bl:
        paras = "<p class='para muted'>No notes for this period.</p>"
    return banner + head + paras + bl


# ── data table (chunked into pages) ───────────────────────────────────────────
def _table_cell_html(col: dict, value) -> str:
    kind = col.get("kind")
    type_ = col.get("type", "text")
    if kind == "delta":
        text, tone = _fmt_delta(type_, value)
        return f'<td class="num"><span class="delta {tone}">{_esc(text)}</span></td>'
    if kind == "metric":
        return f'<td class="num">{_fmt_value(type_, value)}</td>'
    return f'<td>{_esc(value)}</td>'


def _data_table_pages(block: dict, sub: str, rows_per_page: int) -> list:
    """Returns a list of (inner_html) pages for a data_table block."""
    title = block.get("title") or "Table"
    columns = block.get("columns") or []
    if block.get("available") is False:
        return [_section_head(title, sub) + _unavailable(block.get("unavailableReason"))]

    rows = block.get("rows") or []
    head_cells = "".join(
        f'<th class="{ "num" if c.get("kind") in ("metric","delta") else "" }">{_esc(c.get("label"))}</th>'
        for c in columns)
    thead = f"<thead><tr>{head_cells}</tr></thead>"

    if not rows:
        empty = (f'<table class="dt">{thead}<tbody><tr>'
                 f'<td colspan="{len(columns)}" class="empty">No rows for this period.</td>'
                 f'</tr></tbody></table>')
        return [_section_head(title, sub) + empty]

    pages = []
    chunks = _chunk(rows, rows_per_page)
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        body_rows = []
        for r in chunk:
            cells = (r or {}).get("cells") or {}
            tds = "".join(_table_cell_html(c, cells.get(c.get("key"))) for c in columns)
            body_rows.append(f"<tr>{tds}</tr>")
        cont = f" (cont. {i}/{total})" if total > 1 else ""
        table = f'<table class="dt">{thead}<tbody>{"".join(body_rows)}</tbody></table>'
        pages.append(_section_head(title + cont, sub if i == 1 else "") + table)
    return pages


# ── keyword table (green/red change cells), chunked ───────────────────────────
def _keyword_pages(block: dict) -> list:
    title = block.get("title") or "Keyword Rankings"
    sub = "Lower position is better — a green change means the keyword moved up."
    columns = block.get("columns") or []
    if block.get("available") is False:
        return [_section_head(title, sub) + _unavailable(block.get("unavailableReason"))]
    rows = block.get("rows") or []
    head_cells = "".join(
        f'<th class="{ "num" if c.get("kind") in ("metric","delta") else "" }">{_esc(c.get("label"))}</th>'
        for c in columns)
    thead = f"<thead><tr>{head_cells}</tr></thead>"
    if not rows:
        empty = (f'<table class="dt kw">{thead}<tbody><tr>'
                 f'<td colspan="{len(columns)}" class="empty">No tracked keywords for this period.</td>'
                 f'</tr></tbody></table>')
        return [_section_head(title, sub) + empty]

    pages = []
    chunks = _chunk(rows, _KEYWORD_ROWS_PER_PAGE)
    total = len(chunks)
    for i, chunk in enumerate(chunks, 1):
        body_rows = []
        for r in chunk:
            cells = (r or {}).get("cells") or {}
            delta = cells.get("rank_delta")
            # row tone from the change: negative delta = improved = green
            if _num(delta) and delta != 0:
                row_tone = "row-up" if delta < 0 else "row-down"
            else:
                row_tone = ""
            tds = "".join(_table_cell_html(c, cells.get(c.get("key"))) for c in columns)
            body_rows.append(f'<tr class="{row_tone}">{tds}</tr>')
        cont = f" (cont. {i}/{total})" if total > 1 else ""
        table = f'<table class="dt kw">{thead}<tbody>{"".join(body_rows)}</tbody></table>'
        legend = ('<div class="legend">'
                  '<span class="lg up">▲ improved</span>'
                  '<span class="lg down">▼ declined</span>'
                  '<span class="lg flat">— no change</span></div>') if i == 1 else ""
        pages.append(_section_head(title + cont, sub if i == 1 else "") + legend + table)
    return pages


# ── backlinks numbered list, chunked ──────────────────────────────────────────
def _backlinks_pages(block: dict) -> list:
    title = block.get("title") or "New Backlinks"
    items = block.get("items") or []
    count = block.get("count", len(items))
    month = block.get("month")
    sub = f"{count} new backlink{'' if count == 1 else 's'}" + (f" · {month}" if month else "")
    if not items:
        return [_section_head(title, sub)
                + '<div class="unavailable"><span class="ua-icon">—</span>'
                  '<span>No new backlinks were recorded for this period.</span></div>']
    pages = []
    chunks = _chunk(items, _BACKLINKS_PER_PAGE)
    total = len(chunks)
    start = 0
    for i, chunk in enumerate(chunks, 1):
        lis = []
        for j, it in enumerate(chunk, start + 1):
            url = _esc(it.get("url"))
            lis.append(f'<li><span class="bl-n">{j}</span><span class="bl-url">{url}</span></li>')
        start += len(chunk)
        cont = f" (cont. {i}/{total})" if total > 1 else ""
        pages.append(_section_head(title + cont, sub if i == 1 else "")
                     + f'<ol class="backlinks">{"".join(lis)}</ol>')
    return pages


# ── GSC daily trend → inline SVG line chart ───────────────────────────────────
def _chart_page(block: dict) -> str:
    title = block.get("title") or "Daily Trend"
    if block.get("available") is False:
        return _section_head(title) + _unavailable(block.get("unavailableReason"))
    points = block.get("points") or []
    series = block.get("series") or []
    xs = [p.get("x") for p in points]
    # collect numeric series
    svalues = {s["key"]: [p.get(s["key"]) for p in points] for s in series}
    if not points or not series:
        return _section_head(title) + _unavailable("No daily trend for this period.")

    W, H = 940, 360
    pad_l, pad_r, pad_t, pad_b = 48, 16, 16, 40
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    all_vals = [v for vals in svalues.values() for v in vals if _num(v)]
    vmax = max(all_vals) if all_vals else 1
    vmax = vmax or 1
    n = len(points)
    colors = [_BLUE, "#7bb7df"]

    def x_at(i):
        return pad_l + (plot_w * (i / (n - 1)) if n > 1 else plot_w / 2)

    def y_at(v):
        return pad_t + plot_h - (plot_h * (v / vmax) if _num(v) else 0)

    # gridlines + y labels (5 steps)
    grid = []
    for g in range(5):
        gy = pad_t + plot_h * g / 4
        val = round(vmax * (1 - g / 4))
        grid.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{W-pad_r}" y2="{gy:.1f}" class="gl"/>')
        grid.append(f'<text x="{pad_l-8}" y="{gy+4:.1f}" class="yl">{val:,}</text>')

    paths = []
    dots = []
    for si, s in enumerate(series):
        col = colors[si % len(colors)]
        vals = svalues[s["key"]]
        pts = [(x_at(i), y_at(v)) for i, v in enumerate(vals) if _num(v)]
        if pts:
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
            paths.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2"/>')

    # x labels: first / middle / last to avoid clutter
    xlabels = []
    for i in (0, n // 2, n - 1):
        if 0 <= i < n:
            lbl = _esc(xs[i])
            anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
            xlabels.append(f'<text x="{x_at(i):.1f}" y="{H-12}" class="xl" text-anchor="{anchor}">{lbl}</text>')

    legend = "".join(
        f'<span class="lg"><i style="background:{colors[i%len(colors)]}"></i>{_esc(s.get("label"))}</span>'
        for i, s in enumerate(series))

    svg = (f'<svg viewBox="0 0 {W} {H}" class="chart" preserveAspectRatio="xMidYMid meet">'
           f'{"".join(grid)}{"".join(paths)}{"".join(xlabels)}</svg>')
    return _section_head(title) + f'<div class="chart-legend">{legend}</div>' + svg


# ── cover + TOC ───────────────────────────────────────────────────────────────
def _cover_html(header: dict, period_label: str) -> str:
    project = _esc(header.get("projectName") or "Client")
    domain = _esc(header.get("domain") or "")
    period = _esc(period_label or header.get("periodLabel") or "")
    domain_html = f'<div class="cv-domain">{domain}</div>' if domain else ""
    return f"""
    <section class="page cover">
      <div class="cv-circle c1"></div>
      <div class="cv-circle c2"></div>
      <div class="cv-circle c3"></div>
      <div class="cv-inner">
        <div class="cv-logo"><img src="{_logo_uri()}" alt="InfyApp"/></div>
        <div class="cv-spacer"></div>
        <div class="cv-kicker">Monthly SEO Report</div>
        <h1 class="cv-title">SEO Performance<br><span class="thin">Report</span></h1>
        <div class="cv-client">{project}</div>
        {domain_html}
        <div class="cv-period">{period}</div>
        <div class="cv-spacer"></div>
        <div class="cv-foot">
          <span>Prepared by InfyApp</span>
          <span>{period}</span>
        </div>
      </div>
    </section>"""


def _toc_html(entries: list, total: int, period_label: str) -> str:
    rows = "".join(
        f'<li><span class="toc-t">{_esc(title)}</span>'
        f'<span class="toc-dots"></span><span class="toc-p">{page}</span></li>'
        for title, page in entries)
    inner = _section_head("Contents") + f'<ol class="toc">{rows}</ol>'
    return _wrap_content_page(inner, "Contents", 2, total, period_label)


# ── page wrapper ──────────────────────────────────────────────────────────────
def _wrap_content_page(inner: str, running: str, page_num, total, period_label: str) -> str:
    foot_num = f'<span class="ft-pg">{page_num} / {total}</span>' if page_num else "<span></span>"
    return f"""
    <section class="page content">
      <div class="topbar">
        <span class="tb-brand"><img class="tb-logo" src="{_logo_uri()}" alt="InfyApp"/>
          <span class="tb-sep">·</span> SEO Report</span>
        <span class="tb-meta">{_esc(running)}</span>
      </div>
      <div class="page-body">{inner}</div>
      <div class="footer">
        <span class="ft-left">InfyApp Monthly SEO Report — {_esc(period_label)}</span>
        {foot_num}
      </div>
    </section>"""


# ── CSS ───────────────────────────────────────────────────────────────────────
def _css() -> str:
    vars_css = f""":root{{
      --blue:{_BLUE};--blue-dark:{_BLUE_DARK};--blue-deep:{_BLUE_DEEP};
      --blue-tint:{_BLUE_TINT};--blue-tint2:{_BLUE_TINT2};--charcoal:{_CHARCOAL};
      --ink:{_INK};--muted:{_MUTED};--border:{_BORDER};--bg-soft:{_BG_SOFT};
      --green:{_GREEN};--green-bg:{_GREEN_BG};--red:{_RED};--red-bg:{_RED_BG};
    }}"""
    body_css = """
    *{box-sizing:border-box;}
    html,body{margin:0;padding:0;font-family:'Poppins',Arial,Helvetica,sans-serif;
      color:var(--ink);-webkit-print-color-adjust:exact;print-color-adjust:exact;}
    .page{width:210mm;min-height:297mm;page-break-after:always;position:relative;overflow:hidden;}
    .page:last-child{page-break-after:auto;}

    /* ── Cover ── */
    .cover{background:linear-gradient(155deg,var(--blue) 0%,var(--blue-deep) 100%);color:#fff;}
    .cv-circle{position:absolute;border-radius:50%;}
    .c1{width:360mm;height:360mm;right:-150mm;top:-130mm;background:rgba(255,255,255,.07);}
    .c2{width:230mm;height:230mm;left:-95mm;bottom:-80mm;background:rgba(255,255,255,.05);}
    .c3{width:92mm;height:92mm;right:22mm;bottom:46mm;border:2px solid rgba(255,255,255,.22);}
    .cv-inner{position:relative;z-index:2;padding:24mm 22mm;height:297mm;display:flex;flex-direction:column;}
    .cv-logo{background:#fff;border-radius:14px;padding:12px 22px;display:inline-flex;align-self:flex-start;
      box-shadow:0 6px 22px rgba(0,0,0,.18);}
    .cv-logo img{height:60px;display:block;}
    .cv-spacer{flex:1;}
    .cv-kicker{text-transform:uppercase;letter-spacing:5px;font-size:12px;font-weight:500;opacity:.9;margin-bottom:10px;}
    .cv-title{font-size:52px;line-height:1.03;margin:0 0 6px;font-weight:700;letter-spacing:-.5px;}
    .cv-title .thin{font-weight:300;opacity:.92;}
    .cv-client{font-size:24px;font-weight:600;margin-top:30px;}
    .cv-domain{font-size:14px;opacity:.85;margin-top:3px;letter-spacing:.3px;}
    .cv-period{margin-top:20px;display:inline-block;align-self:flex-start;background:rgba(255,255,255,.16);
      border:1px solid rgba(255,255,255,.28);padding:9px 18px;border-radius:999px;font-size:14px;font-weight:500;}
    .cv-foot{display:flex;justify-content:space-between;font-size:11px;opacity:.85;
      border-top:1px solid rgba(255,255,255,.25);padding-top:12px;}

    /* ── Content shell ── */
    .content{background:#fff;}
    .topbar{position:absolute;top:0;left:0;right:0;height:18mm;padding:0 16mm;display:flex;
      align-items:center;justify-content:space-between;border-bottom:2px solid var(--blue);}
    .tb-brand{display:flex;align-items:center;gap:6px;font-weight:600;color:var(--blue-dark);font-size:12px;letter-spacing:.3px;}
    .tb-logo{height:22px;display:block;}
    .tb-sep{color:var(--muted);}
    .tb-meta{font-size:11px;color:var(--muted);}
    .page-body{padding:24mm 16mm 20mm;}

    h2.section{display:flex;align-items:center;gap:10px;font-size:21px;color:var(--blue-dark);
      margin:0 0 4px;font-weight:600;letter-spacing:-.2px;}
    h2.section .bar{display:inline-block;width:5px;height:22px;background:var(--blue);border-radius:3px;}
    .sub{color:var(--muted);font-size:12.5px;margin:0 0 18px;}
    .para{font-size:13px;line-height:1.65;margin:0 0 11px;color:#3a4150;}
    .para.muted{color:var(--muted);}
    .bullets{margin:6px 0 0;padding-left:0;list-style:none;}
    .bullets li{font-size:13px;line-height:1.55;margin:0 0 8px;padding-left:22px;position:relative;color:#3a4150;}
    .bullets li:before{content:"";position:absolute;left:4px;top:7px;width:7px;height:7px;border-radius:50%;background:var(--blue);}

    .unavailable{display:flex;align-items:center;gap:10px;background:var(--bg-soft);border:1px solid var(--border);
      border-radius:10px;padding:16px 18px;color:var(--muted);font-size:13px;margin-top:6px;}
    .ua-icon{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;border-radius:50%;
      background:#fff;border:1px solid var(--border);font-weight:700;color:var(--muted);}

    /* ── Metric grid ── */
    .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:13px;margin-top:6px;}
    .card{border:1px solid var(--border);border-radius:12px;padding:15px 17px;background:#fff;
      border-top:3px solid var(--blue);}
    .card-label{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;font-weight:500;}
    .card-value{font-size:30px;font-weight:600;margin:5px 0 4px;color:#11151c;}
    .card-row{display:flex;justify-content:space-between;align-items:baseline;font-size:12px;}
    .prev{color:var(--muted);}
    .delta{font-weight:600;}
    .delta.up{color:var(--green);}
    .delta.down{color:var(--red);}
    .delta.flat{color:var(--muted);}

    /* ── Data tables ── */
    table.dt{width:100%;border-collapse:collapse;margin-top:8px;font-size:11.5px;}
    table.dt th{background:var(--blue-tint);color:var(--blue-dark);text-align:left;font-weight:600;
      padding:9px 10px;border-bottom:2px solid var(--blue);font-size:11px;letter-spacing:.2px;}
    table.dt td{padding:8px 10px;border-bottom:1px solid var(--border);color:#3a4150;}
    table.dt th.num,table.dt td.num{text-align:right;font-variant-numeric:tabular-nums;}
    table.dt tbody tr:nth-child(even){background:var(--blue-tint2);}
    table.dt td.empty{text-align:center;color:var(--muted);padding:18px;}
    table.kw tbody tr.row-up{background:var(--green-bg);}
    table.kw tbody tr.row-down{background:var(--red-bg);}
    .legend{display:flex;gap:14px;margin:8px 0 0;font-size:11px;}
    .legend .lg{display:inline-flex;align-items:center;gap:4px;color:var(--muted);}
    .legend .lg.up{color:var(--green);}
    .legend .lg.down{color:var(--red);}

    /* ── Backlinks ── */
    ol.backlinks{list-style:none;margin:8px 0 0;padding:0;column-count:1;}
    ol.backlinks li{display:flex;align-items:baseline;gap:10px;padding:6px 0;border-bottom:1px dotted var(--border);font-size:11.5px;}
    .bl-n{flex:0 0 26px;color:var(--blue);font-weight:600;text-align:right;font-variant-numeric:tabular-nums;}
    .bl-url{word-break:break-all;color:#3a4150;}

    /* ── Chart ── */
    .chart-legend{display:flex;gap:16px;margin:6px 0 4px;font-size:12px;color:var(--muted);}
    .chart-legend .lg{display:inline-flex;align-items:center;gap:6px;}
    .chart-legend .lg i{width:14px;height:3px;border-radius:2px;display:inline-block;}
    svg.chart{width:100%;height:auto;margin-top:6px;}
    svg.chart .gl{stroke:var(--border);stroke-width:1;}
    svg.chart .yl{fill:var(--muted);font-size:10px;text-anchor:end;}
    svg.chart .xl{fill:var(--muted);font-size:10px;}

    /* ── TOC ── */
    ol.toc{list-style:none;margin:10px 0 0;padding:0;counter-reset:toc;}
    ol.toc li{display:flex;align-items:baseline;gap:8px;padding:10px 0;border-bottom:1px solid var(--border);font-size:13.5px;}
    ol.toc li:before{counter-increment:toc;content:counter(toc,decimal-leading-zero);color:var(--blue);font-weight:600;
      flex:0 0 30px;font-size:12px;}
    .toc-t{color:#3a4150;font-weight:500;}
    .toc-dots{flex:1;border-bottom:1px dotted var(--border);transform:translateY(-4px);}
    .toc-p{color:var(--muted);font-variant-numeric:tabular-nums;}

    /* ── Banner (maturing notice) ── */
    .banner{background:var(--blue-tint);border:1px solid var(--blue);border-left:4px solid var(--blue);
      border-radius:8px;padding:11px 14px;font-size:12px;color:var(--blue-dark);margin-bottom:16px;}

    /* ── Footer ── */
    .footer{position:absolute;bottom:0;left:0;right:0;height:14mm;padding:0 16mm;display:flex;align-items:center;
      justify-content:space-between;font-size:10px;color:var(--muted);border-top:1px solid var(--border);}
    .ft-pg{font-variant-numeric:tabular-nums;font-weight:500;}
    """
    return _font_face_css() + vars_css + body_css


# ── document assembly ─────────────────────────────────────────────────────────
def _build_section_pages(content: dict, period_label: str, prev_label: str):
    """Walk the block document and produce an ordered list of
    (section_title, inner_html) — one entry per PHYSICAL page (long blocks split)."""
    header = _header_block(content)
    maturing = header.get("maturingNotice") if header.get("maturing") else None
    banner = f'<div class="banner">{_esc(maturing)}</div>' if maturing else ""

    vs_sub = (f"Current period vs. previous ({_esc(prev_label)})"
              if prev_label else "Current period vs. previous period")

    pages = []  # (section_title, inner_html)
    first_content = True

    for b in _blocks(content):
        btype = b.get("type")
        if btype == "report_header":
            continue
        bnr = banner if first_content else ""
        if btype == "narrative":
            title = b.get("title") or "Notes"
            pages.append((title, _narrative_page(b, bnr)))
            first_content = False
        elif btype == "metric_grid":
            title = b.get("title") or "Metrics"
            pages.append((title, bnr + _metric_grid_page(b, vs_sub)))
            first_content = False
        elif btype == "data_table":
            if b.get("id") == "keywords":
                inner_pages = _keyword_pages(b)
            else:
                inner_pages = _data_table_pages(b, "", _TABLE_ROWS_PER_PAGE)
            title = b.get("title") or "Table"
            for k, inner in enumerate(inner_pages):
                pages.append((title, (bnr if k == 0 else "") + inner))
            first_content = False
        elif btype == "chart":
            title = b.get("title") or "Chart"
            pages.append((title, bnr + _chart_page(b)))
            first_content = False
        elif btype == "backlinks_list":
            title = b.get("title") or "Backlinks"
            for k, inner in enumerate(_backlinks_pages(b)):
                pages.append((title, (bnr if k == 0 else "") + inner))
            first_content = False
    return pages


def render_html(version: dict) -> str:
    """Build the full print HTML (cover + TOC + every section) from a version dict
    carrying `content` (the report_document) and `data` (frozen blob)."""
    content = version.get("content") or {}
    header = _header_block(content)
    period_label = (content.get("period_label") or header.get("periodLabel")
                    or version.get("periodKey") or "")
    prev_label = content.get("prev_period_label") or header.get("prevPeriodLabel") or ""

    section_pages = _build_section_pages(content, period_label, prev_label)

    # Page numbering: cover = p1, TOC = p2, content from p3. total known up front.
    content_start = 3
    total = 2 + len(section_pages)

    # TOC entries: first physical page of each distinct section title.
    toc_entries = []
    seen = set()
    for i, (title, _inner) in enumerate(section_pages):
        page_no = content_start + i
        if title not in seen:
            seen.add(title)
            toc_entries.append((title, page_no))

    # Assemble.
    parts = [_cover_html(header, period_label), _toc_html(toc_entries, total, period_label)]
    for i, (title, inner) in enumerate(section_pages):
        page_no = content_start + i
        parts.append(_wrap_content_page(inner, title, page_no, total, period_label))

    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{_css()}</style></head><body>{"".join(parts)}</body></html>')


# ── PDF conversion (Playwright / headless Chromium) ────────────────────────────
def render_pdf(version: dict) -> bytes:
    """Render the report HTML to PDF bytes via headless Chromium. A4, real
    background colors (print_background) so the cover motif renders. Launches a
    fresh browser per call (on-demand; nothing cached or stored). MUST be called
    from a SYNC context (no running asyncio loop) — the PDF endpoint is a sync
    FastAPI handler, which FastAPI runs in a worker thread."""
    from playwright.sync_api import sync_playwright

    html_str = render_html(version)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html_str, wait_until="load")
            page.emulate_media(media="print")
            pdf = page.pdf(format="A4", print_background=True,
                           margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
        finally:
            browser.close()
    return pdf


def pdf_filename(version: dict) -> str:
    """`{project}-{period}-seo-report.pdf`, slugified for a safe download name."""
    content = version.get("content") or {}
    data = version.get("data") or {}
    header = _header_block(content)
    project = (header.get("projectName")
               or (data.get("project") or {}).get("name")
               or "report")
    period = content.get("period_key") or version.get("periodKey") or "period"

    def slug(s: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
        return s or "report"

    return f"{slug(project)}-{slug(period)}-seo-report.pdf"
