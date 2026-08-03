import base64
import html
import re

from ..config import AGENCY_NAME
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets"

_BLUE = "#5980a6"
_BLUE_HEAD = "#5980a6"
_BLUE_DARK = "#4a6d90"
_BLUE_DEEP = "#0a2540"
_BLUE_TINT = "#eef2f7"
_BLUE_TINT2 = "#f8fafb"
_CHARCOAL = "#424242"
_INK = "#2a2f36"
_BODY = "#1d1f20"
_MUTED = "#8a8a8d"
_GA = "#3a3f45"
_BORDER = "#e4e4e6"
_BG_SOFT = "#f5f7f9"
_GREEN = "#15b41f"
_GREEN_BG = "#e3f7e5"
_RED = "#e0362c"
_RED_BG = "#fdecea"

_AGENCY_PHONE = "+91 7304 5050 68"
_AGENCY_EMAIL = "info@infyappdevelopment.com"
_AGENCY_SITE = "infyappdevelopment.com"
_AGENCY_ADDR = "211, Lotus Business Park, Rambaugh Lane,\n Next to Chincholi Signal Petrol Pump,\nMalad West - 400064"

_TABLE_ROWS_PER_PAGE = 20
_KEYWORD_ROWS_PER_PAGE = 22
_BACKLINKS_PER_PAGE = 30


@lru_cache(maxsize=None)
def _data_uri(filename: str, mime: str) -> str:
    raw = (_ASSETS / filename).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


@lru_cache(maxsize=1)
def _logo_uri() -> str:
    return _data_uri("infapp-logo-trimmed.png", "image/png")


@lru_cache(maxsize=1)
def _toc_hero_uri():
    for name, mime in (("seo-hero.png", "image/png"), ("seo-hero.jpg", "image/jpeg"),
                       ("seo-hero.jpeg", "image/jpeg"), ("seo-hero.webp", "image/webp")):
        if (_ASSETS / name).exists():
            return _data_uri(name, mime)
    return None


@lru_cache(maxsize=1)
def _wave_uri():
    return _data_uri("wave.png", "image/png") if (_ASSETS / "wave.png").exists() else None


@lru_cache(maxsize=1)
def _font_face_css() -> str:
    weights = [
        ("Poppins-Light.ttf", 300),
        ("Poppins-Regular.ttf", 400),
        ("Poppins-Medium.ttf", 500),
        ("Poppins-SemiBold.ttf", 600),
        ("Poppins-Bold.ttf", 700),
        ("Poppins-ExtraBold.ttf", 800),
        ("Poppins-Black.ttf", 900),
    ]
    faces = []
    for fname, weight in weights:
        uri = _data_uri(fname, "font/ttf")
        faces.append(
            "@font-face{font-family:'Poppins';font-style:normal;"
            f"font-weight:{weight};src:url({uri}) format('truetype');}}"
        )
    return "".join(faces)


import math  # noqa: E402  (local to the decorative helpers below)


@lru_cache(maxsize=8)
def _halftone_dots(big: str = "left") -> str:
    R, step, rmin, rmax = 150, 9, 0.4, 3.6
    out = []
    x = -R
    while x <= R:
        y = -R
        while y <= R:
            d = math.hypot(x, y)
            if d <= R:
                t = (x + R) / (2 * R)
                f = (1 - t) if big == "left" else t
                r = (rmin + (rmax - rmin) * f) * (1 - (d / R) * 0.15)
                if r > 0.3:
                    out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{r:.2f}"/>')
            y += step
        x += step
    return "".join(out)


def _halftone_svg(cls: str, big: str = "left") -> str:
    return (f'<svg class="{cls}" viewBox="-155 -155 310 310" xmlns="http://www.w3.org/2000/svg">'
            f'<g fill="{_BLUE}">{_halftone_dots(big)}</g></svg>')


def _ellipses_svg() -> str:
    return (f'<svg class="cv-ellipses" viewBox="0 0 320 360" xmlns="http://www.w3.org/2000/svg">'
            f'<ellipse cx="-20" cy="180" rx="70" ry="150" fill="{_BLUE}"/>'
            f'<ellipse cx="115" cy="180" rx="70" ry="150" fill="{_BLUE}"/>'
            f'<ellipse cx="250" cy="180" rx="70" ry="150" fill="{_BLUE}"/></svg>')


def _arrow_svg() -> str:
    return (f'<svg class="cv-arrow" viewBox="0 0 48 40" xmlns="http://www.w3.org/2000/svg" fill="{_BLUE}">'
            f'<path d="M0 15h30V4l18 16-18 16V25H0z"/></svg>')


_MONTHS = ("January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December")


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _period_range_label(period_key: str, period_label: str) -> str:
    try:
        import calendar
        y_s, m_s = str(period_key).split("-")
        y, m = int(y_s), int(m_s)
        if not (1 <= m <= 12):
            raise ValueError
        last = calendar.monthrange(y, m)[1]
        name = _MONTHS[m - 1]
        return f"{_ordinal(1)} {name} {y} - {_ordinal(last)} {name} {y}"
    except Exception:
        return period_label or ""


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _human_duration(seconds, signed: bool = False) -> str:
    total = int(round(abs(seconds)))
    minutes, secs = divmod(total, 60)
    if minutes == 0:
        body = f"{secs}s"
    elif secs == 0:
        body = f"{minutes}m"
    else:
        body = f"{minutes}m {secs}s"
    prefix = "-" if seconds < 0 else ("+" if signed and seconds > 0 else "")
    return prefix + body


def _fmt_value(type_: str, v) -> str:
    if not _num(v):
        return "—"
    try:
        if type_ == "count":
            return f"{round(v):,}"
        if type_ == "duration":
            return _human_duration(v)
        if type_ == "percent":
            return f"{round(v * 100, 2)}%"
        if type_ == "rank":
            return f"#{round(v)}"
        return html.escape(str(v))
    except Exception:
        return html.escape(str(v))


def _fmt_delta(type_: str, d):
    if not _num(d) or d == 0:
        return ("—", "flat")
    improved = (d < 0) if type_ == "rank" else (d > 0)
    tone = "up" if improved else "down"
    s = "+" if d > 0 else ""
    if type_ == "count":
        text = f"{s}{round(d):,}"
    elif type_ == "duration":
        text = _human_duration(d, signed=True)
    elif type_ == "percent":
        text = f"{s}{round(d * 100, 2)}%"
    elif type_ == "rank":
        arrow = '<span class="tri t-up"></span>' if improved else '<span class="tri t-down"></span>'
        text = arrow + str(abs(round(d, 1)))
    else:
        text = html.escape(str(d))
    return (text, tone)


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


_DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)


def _safe_image_src(v) -> str:
    s = "" if v is None else str(v)
    return _esc(s) if _DATA_IMAGE_RE.match(s) else ""


def _chunk(seq, n):
    seq = seq or []
    return [seq[i:i + n] for i in range(0, len(seq), n)] or [[]]


def _included(item) -> bool:
    return (item or {}).get("included", True) is not False


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


def _unavailable(reason: str) -> str:
    return (f'<div class="unavailable"><span class="ua-icon">—</span>'
            f'<span>{_esc(reason or "Not available for this period.")}</span></div>')


def _section_head(title: str, sub: str = "") -> str:
    if not (title or "").strip():
        return ""
    sub_html = f'<p class="sub">{_esc(sub)}</p>' if sub else ""
    return f'<h2 class="section">{_esc(title)}</h2>{sub_html}'


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


def _metric_grid_page(grid: dict, sub: str = "", period_label: str = "", prev_label: str = "") -> str:
    title = (grid or {}).get("title") or ""
    head = f'<h2 class="section">{_esc(title)}</h2>' if (title or "").strip() else ""
    if not grid or grid.get("available") is False:
        return head + _unavailable((grid or {}).get("unavailableReason"))
    metrics = grid.get("metrics") or []

    def column(month_label, use_prev):
        cells = []
        for m in metrics:
            type_ = m.get("type", "count")
            val = m.get("previousValue") if use_prev else m.get("currentValue")
            cells.append(
                f'<div class="cmp-metric"><div class="cmp-l">{_esc(m.get("label"))}</div>'
                f'<div class="cmp-v">{_fmt_value(type_, val)}</div></div>')
        return f'<div><h3 class="cmp-head">{_esc(month_label)}</h3>{"".join(cells)}</div>'

    prev_h = f"Previous Month ({(prev_label or 'previous').replace(' ', '-')})"
    curr_h = f"Current Month ({(period_label or 'current').replace(' ', '-')})"
    return head + f'<div class="cmp-grid">{column(prev_h, True)}{column(curr_h, False)}</div>'


def _resolve_chip(node, blobs_by_name) -> str:
    attrs = node.get("attrs") or {}
    name, kind, label = attrs.get("name"), attrs.get("kind"), attrs.get("label")
    blob = (blobs_by_name or {}).get(name)
    if not blob:
        return f"<span>{_esc(label or name or '?')}</span>"
    type_ = blob.get("type", "text")
    if kind == "delta":
        text, _tone = _fmt_delta(type_, blob.get("deltaValue"))
    else:
        text = _fmt_value(type_, blob.get("currentValue"))
    return f"<strong>{_esc(text)}</strong>"


def _render_inline(nodes, blobs_by_name) -> str:
    out = []
    for n in nodes or []:
        t = n.get("type")
        if t == "text":
            s = _esc(n.get("text") or "")
            for m in n.get("marks") or []:
                mt = m.get("type")
                if mt == "bold":
                    s = f"<strong>{s}</strong>"
                elif mt == "italic":
                    s = f"<em>{s}</em>"
                elif mt == "strike":
                    s = f"<s>{s}</s>"
                elif mt == "code":
                    s = f"<code>{s}</code>"
            out.append(s)
        elif t == "blob":
            out.append(_resolve_chip(n, blobs_by_name))
        elif t == "hardBreak":
            out.append("<br>")
        elif n.get("content"):
            out.append(_render_inline(n.get("content"), blobs_by_name))
    return "".join(out)


def _render_li(li, blobs_by_name) -> str:
    return "".join(_render_inline(ch.get("content"), blobs_by_name)
                   for ch in (li.get("content") or []))


def _render_doc(doc, blobs_by_name) -> str:
    parts = []
    for node in doc.get("content") or []:
        t = node.get("type")
        inner = node.get("content")
        if t == "paragraph":
            parts.append(f"<p class='para'>{_render_inline(inner, blobs_by_name)}</p>")
        elif t == "heading":
            parts.append(f"<p class='para'><strong>{_render_inline(inner, blobs_by_name)}</strong></p>")
        elif t in ("bulletList", "orderedList"):
            tag = "ul" if t == "bulletList" else "ol"
            lis = "".join(f"<li>{_render_li(li, blobs_by_name)}</li>" for li in inner or [])
            parts.append(f"<{tag} class='bullets'>{lis}</{tag}>")
        elif t == "blockquote":
            parts.append(f"<p class='para'>{_render_inline(inner, blobs_by_name)}</p>")
        elif inner:
            parts.append(f"<p class='para'>{_render_inline(inner, blobs_by_name)}</p>")
    return "".join(parts)


def _narrative_page(block: dict, banner: str = "", blobs_by_name=None) -> str:
    head = _section_head(block.get("title") or "")
    doc = block.get("doc")
    if isinstance(doc, dict) and doc.get("type") == "doc":
        body = _render_doc(doc, blobs_by_name or {})
        if not body.strip():
            body = "<p class='para muted'>No notes for this period.</p>"
        return banner + head + body
    paras = "".join(f"<p class='para'>{_esc(p)}</p>" for p in (block.get("paragraphs") or []))
    bullets = block.get("bullets") or []
    bl = ""
    if bullets:
        items = "".join(f"<li>{_esc(b)}</li>" for b in bullets)
        bl = f"<ul class='bullets'>{items}</ul>"
    if not paras and not bl:
        paras = "<p class='para muted'>No notes for this period.</p>"
    return banner + head + paras + bl


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
    title = block.get("title") or ""
    columns = block.get("columns") or []
    if block.get("available") is False:
        return [_section_head(title, sub) + _unavailable(block.get("unavailableReason"))]

    all_rows = block.get("rows") or []
    rows = [r for r in all_rows if _included(r)]
    head_cells = "".join(
        f'<th class="{ "num" if c.get("kind") in ("metric","delta") else "" }">{_esc(c.get("label"))}</th>'
        for c in columns)
    thead = f"<thead><tr>{head_cells}</tr></thead>"

    if not rows:
        msg = ("No rows selected for this period." if all_rows
               else "No rows for this period.")
        empty = (f'<table class="dt">{thead}<tbody><tr>'
                 f'<td colspan="{len(columns)}" class="empty">{msg}</td>'
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
        pages.append(_section_head((title + cont) if title.strip() else "", sub if i == 1 else "") + table)
    return pages


def _keyword_pages(block: dict) -> list:
    title = block.get("title") or ""
    sub = "Lower position is better — a green change means the keyword moved up."
    columns = block.get("columns") or []
    if block.get("available") is False:
        return [_section_head(title, sub) + _unavailable(block.get("unavailableReason"))]
    all_rows = block.get("rows") or []
    rows = [r for r in all_rows if _included(r)]
    head_cells = "".join(
        f'<th class="{ "num" if c.get("kind") in ("metric","delta") else "" }">{_esc(c.get("label"))}</th>'
        for c in columns)
    thead = f"<thead><tr>{head_cells}</tr></thead>"
    if not rows:
        msg = ("No keywords selected for this period." if all_rows
               else "No tracked keywords for this period.")
        empty = (f'<table class="dt kw">{thead}<tbody><tr>'
                 f'<td colspan="{len(columns)}" class="empty">{msg}</td>'
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
            if _num(delta) and delta != 0:
                row_tone = "row-up" if delta < 0 else "row-down"
            else:
                row_tone = ""
            tds = "".join(_table_cell_html(c, cells.get(c.get("key"))) for c in columns)
            body_rows.append(f'<tr class="{row_tone}">{tds}</tr>')
        cont = f" (cont. {i}/{total})" if total > 1 else ""
        table = f'<table class="dt kw">{thead}<tbody>{"".join(body_rows)}</tbody></table>'
        legend = ('<div class="legend">'
                  '<span class="lg up"><span class="tri t-up"></span> improved</span>'
                  '<span class="lg down"><span class="tri t-down"></span> declined</span>'
                  '<span class="lg flat">— no change</span></div>') if i == 1 else ""
        pages.append(_section_head((title + cont) if title.strip() else "", sub if i == 1 else "") + legend + table)
    return pages


def _backlinks_pages(block: dict, extra_head_px: float = 0.0) -> list:
    title = block.get("title") or ""
    all_items = block.get("items") or []
    items = [it for it in all_items if _included(it)]
    count = block.get("count", len(all_items))
    shown = len(items)
    month = block.get("month")
    noun = block.get("noun")
    if noun:
        sub = f"{count} {noun}{'' if count == 1 else 's'}"
    else:
        sub = f"{count} new backlink{'' if count == 1 else 's'}"
    if shown != count:
        sub += f" · showing {shown} of {count}"
    if month:
        sub += f" · {month}"
    if not items:
        if noun:
            msg = f"No {noun}s added yet."
        else:
            msg = ("No backlinks selected for this period." if all_items
                   else "No new backlinks were recorded for this period.")
        return [_section_head(title, sub)
                + '<div class="unavailable"><span class="ua-icon">—</span>'
                  f'<span>{_esc(msg)}</span></div>']
    def _bl_height(url):
        import math as _m
        return max(1, _m.ceil(len(url or "") / 88)) * 16 + 12

    HEAD_PX, BUDGET_PX = 64, _PAGE_BUDGET
    chunks, cur, used = [], [], HEAD_PX + extra_head_px
    for it in items:
        h = _bl_height(it.get("url"))
        if cur and used + h > BUDGET_PX:
            chunks.append(cur)
            cur, used = [], HEAD_PX
        cur.append(it)
        used += h
    if cur:
        chunks.append(cur)

    pages = []
    total = len(chunks)
    start = 0
    for i, chunk in enumerate(chunks, 1):
        lis = []
        for j, it in enumerate(chunk, start + 1):
            url = _esc(it.get("url"))
            lis.append(f'<li><span class="bl-n">{j}</span><span class="bl-url">{url}</span></li>')
        start += len(chunk)
        cont = f" (cont. {i}/{total})" if total > 1 else ""
        pages.append(_section_head((title + cont) if title.strip() else "", sub if i == 1 else "")
                     + f'<ol class="backlinks">{"".join(lis)}</ol>')
    return pages


def _chart_page(block: dict) -> str:
    title = block.get("title") or ""
    if block.get("available") is False:
        return _section_head(title) + _unavailable(block.get("unavailableReason"))
    points = block.get("points") or []
    series = block.get("series") or []
    xs = [p.get("x") for p in points]
    svalues = {s["key"]: [p.get(s["key"]) for p in points] for s in series}
    if not points or not series:
        return _section_head(title) + _unavailable("No daily trend for this period.")

    per_series = block.get("normalize") == "series"
    W, H = 940, 360
    pad_l = 18 if per_series else 48
    pad_r, pad_t, pad_b = 16, 16, 40
    plot_w = W - pad_l - pad_r
    plot_h = H - pad_t - pad_b
    n = len(points)
    colors = [_BLUE, "#7bb7df", "#15b41f", "#e8862b", "#8b5cf6"]

    def x_at(i):
        return pad_l + (plot_w * (i / (n - 1)) if n > 1 else plot_w / 2)

    all_vals = [v for vals in svalues.values() for v in vals if _num(v)]
    vmax = (max(all_vals) if all_vals else 1) or 1

    grid = []
    for g in range(5):
        gy = pad_t + plot_h * g / 4
        grid.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{W-pad_r}" y2="{gy:.1f}" class="gl"/>')
        if not per_series:
            val = round(vmax * (1 - g / 4))
            grid.append(f'<text x="{pad_l-8}" y="{gy+4:.1f}" class="yl">{val:,}</text>')

    paths = []
    for si, s in enumerate(series):
        col = colors[si % len(colors)]
        vals = svalues[s["key"]]
        nums = [v for v in vals if _num(v)]
        if per_series and nums:
            lo, hi = min(nums), max(nums)
            span = (hi - lo) or 1

            def y_at(v, lo=lo, span=span):
                return pad_t + plot_h - plot_h * ((v - lo) / span)
        else:
            def y_at(v):
                return pad_t + plot_h - (plot_h * (v / vmax))
        pts = [(x_at(i), y_at(v)) for i, v in enumerate(vals) if _num(v)]
        if pts:
            d = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in pts)
            paths.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2.2"/>')

    xlabels = []
    for i in (0, n // 2, n - 1):
        if 0 <= i < n:
            lbl = _esc(xs[i])
            anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
            xlabels.append(
                f'<text x="{x_at(i):.1f}" y="{H-12}" class="xl" text-anchor="{anchor}">{lbl}</text>')

    legend = "".join(
        f'<span class="lg"><i style="background:{colors[i%len(colors)]}"></i>{_esc(s.get("label"))}</span>'
        for i, s in enumerate(series))

    svg = (f'<svg viewBox="0 0 {W} {H}" class="chart" preserveAspectRatio="xMidYMid meet">'
           f'{"".join(grid)}{"".join(paths)}{"".join(xlabels)}</svg>')
    return (_section_head(title)
            + f'<div class="chart-card"><div class="chart-legend">{legend}</div>{svg}</div>')


def _cover_html(header: dict, period_label: str, period_range: str) -> str:
    project = _esc(header.get("projectName") or "Client")
    domain = _esc(header.get("domain") or "")
    month = _esc(period_label or header.get("periodLabel") or "")
    domain_html = f'<div class="cv-domain">{domain}</div>' if domain else ""
    client_logo = _safe_image_src(header.get("clientLogo"))
    client_logo_html = (f'<img class="cv-client-logo" src="{client_logo}" alt="Client"/>'
                        if client_logo else '<span class="cv-client-logo-ph"></span>')
    wave_uri = _wave_uri()
    wave_html = f'<img class="cv-wave" src="{wave_uri}" alt=""/>' if wave_uri else ""
    return f"""
    <section class="page cover{' has-wave' if wave_uri else ''}">
      {wave_html}
      {_ellipses_svg()}
      {_halftone_svg("cv-dots", "left")}
      <div class="cv-top">{client_logo_html}<img class="cv-logo" src="{_logo_uri()}" alt="InfyApp"/></div>
      <div class="cv-title-wrap">
        <h1 class="cv-title">Monthly <span class="cv-seo">SEO</span><br>Report</h1>
        <div class="cv-sub">{month}</div>
      </div>
      <div class="cv-client-wrap">
        <div class="cv-label">Prepared for</div>
        <div class="cv-client">{project}</div>
        {domain_html}
      </div>
      <div class="cv-period">
        <div class="cv-label">Reporting Period</div>
        <div class="cv-period-val">{_esc(period_range)}</div>
      </div>
      <div class="cv-prep">
        <div class="cv-label">Prepared by</div>
        <div class="cv-prep-name">{_esc(AGENCY_NAME)}</div>
      </div>
      {_arrow_svg()}
    </section>"""


def _ci_svg(body: str) -> str:
    return (
        '<svg class="ci" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
        'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">' + body + '</svg>'
    )


_IC_PHONE = _ci_svg(
    '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2'
    'A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8.1 9.6a16 16 0 0 0 6 6l1.2-1.2'
    'a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z"/>'
)
_IC_MAIL = _ci_svg('<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2.5 6.5 9.5 7 9.5-7"/>')
_IC_GLOBE = _ci_svg(
    '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19"/>'
    '<path d="M12 2.5a15 15 0 0 1 0 19 15 15 0 0 1 0-19z"/>'
)
_IC_PIN = _ci_svg(
    '<path d="M20 10.5c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10.5" r="2.8"/>'
)


def _thankyou_html() -> str:
    return f"""
    <section class="page thankyou">
      <div class="ty-logo"><img src="{_logo_uri()}" alt="InfyApp"/></div>
      {_halftone_svg("ty-dots-tr", "right")}
      {_halftone_svg("ty-dots-bl", "left")}
      <div class="ty-body">
        <h1 class="ty-title">Thank you!</h1>
        <p class="ty-p">Thank you for taking the time to read this report. If you have
        any questions or would like to discuss our findings further, please don't
        hesitate to reach out to us.</p>
      </div>
      <div class="ty-contact">
        <div>{_IC_PHONE} {_esc(_AGENCY_PHONE)}</div>
        <div>{_IC_MAIL} {_esc(_AGENCY_EMAIL)}</div>
        <div>{_IC_GLOBE} <u>{_esc(_AGENCY_SITE)}</u></div>
        <div>{_IC_PIN} {_esc(_AGENCY_ADDR)}</div>
      </div>
    </section>"""


def _toc_html(entries: list, period_range: str, page_no=None, total=None) -> str:
    half = (len(entries) + 1) // 2
    cols = (entries[:half], entries[half:])

    def col(items):
        return "".join(
            f'<div class="toc-row"><span class="toc-n">{page:02d}</span>'
            f'<span class="toc-t">{_esc(title)}</span></div>'
            for title, page in items)

    hero_uri = _toc_hero_uri()
    if hero_uri:
        hero = f'<img class="toc-hero-img" src="{hero_uri}" alt="SEO"/>'
    else:
        hero = (f'<div class="toc-hero">'
                f'<img class="toc-hero-logo" src="{_logo_uri()}" alt="InfyApp"/>'
                f'<span class="toc-seo">SEO</span></div>')
    inner = (hero + _section_head("Table of Contents")
             + f'<div class="toc-cols"><div>{col(cols[0])}</div>'
               f'<div>{col(cols[1])}</div></div>')
    return _wrap_content_page(inner, period_range, page_no, total)


def _wrap_content_page(inner: str, period_range: str, page_no=None, total=None,
                       *, project_name: str = "", domain: str = "", client_logo: str = "",
                       prepared_by: str = AGENCY_NAME, left_logo: str = "", right_logo: str = "") -> str:
    pg = f"{page_no} / {total}" if page_no and total else (str(page_no) if page_no else "")
    title = _esc(f"{project_name} · Monthly SEO Report".strip(" ·").upper())

    left_url = left_logo or client_logo
    right_url = right_logo or _logo_uri()

    def _slot(url):
        return (f'<div class="rh-logo"><img src="{_esc(url)}" alt=""></div>'
                if url else '<div class="rh-logo rh-empty"></div>')

    left = f"Reporting period: {_esc(period_range)}"
    if prepared_by and project_name:
        left += f" · Prepared by {_esc(prepared_by)} for {_esc(project_name)}"
    return f"""
    <section class="page content">
      <div class="rpt-header">{_slot(left_url)}<div class="rh-title">{title}</div>{_slot(right_url)}</div>
      <div class="page-body">{inner}</div>
      <div class="footer">
        <div class="ft-main"><span>{left}</span><span>{_esc(domain)}</span></div>
        <div class="ft-sub"><span>{_esc(project_name)} — Monthly SEO Report</span><span class="ft-pg">{pg}</span></div>
      </div>
    </section>"""


def _css() -> str:
    vars_css = f""":root{{
      --blue:{_BLUE};--blue-head:{_BLUE_HEAD};--blue-dark:{_BLUE_DARK};--blue-deep:{_BLUE_DEEP};
      --blue-tint:{_BLUE_TINT};--blue-tint2:{_BLUE_TINT2};--charcoal:{_CHARCOAL};
      --ink:{_INK};--body:{_BODY};--muted:{_MUTED};--ga:{_GA};--border:{_BORDER};--bg-soft:{_BG_SOFT};
      --green:{_GREEN};--green-bg:{_GREEN_BG};--red:{_RED};--red-bg:{_RED_BG};--heading-accent:#0066a6;
    }}"""
    body_css = """
    *{box-sizing:border-box;}
    html,body{margin:0;padding:0;font-family:'Barlow',Arial,Helvetica,sans-serif;font-size:14px;
      line-height:1.55;color:var(--ink);-webkit-print-color-adjust:exact;print-color-adjust:exact;}
    h1,h2,h3,h4,h5,h6{font-family:'Barlow Condensed',Arial,sans-serif;font-weight:600;
      line-height:1.12;letter-spacing:-.015em;margin:0 0 7px;}
    .page{width:210mm;height:297mm;page-break-after:always;position:relative;overflow:hidden;background:#fff;}
    .page:last-child{page-break-after:auto;}
    .page-body{padding:28mm 16mm 24mm;}

    /* section eyebrow + heading (industry) */
    .rp-eyebrow{font-family:'Barlow Condensed',Arial,sans-serif;font-weight:600;color:var(--blue);
      font-size:12px;letter-spacing:.09em;text-transform:uppercase;margin:0 0 6px;}
    h2.section{font-size:30px;color:var(--heading-accent);margin:0 0 14px;font-weight:600;letter-spacing:-.015em;line-height:1.1;}
    h2.section.tbl-h{font-size:22px;margin:0 0 8px;}
    .blk{margin-bottom:26px;break-inside:avoid;page-break-inside:avoid;}
    .blk:last-child{margin-bottom:0;}
    .sub{color:var(--muted);font-size:12.5px;font-style:italic;margin:-8px 0 16px;line-height:1.5;max-width:38em;}
    .para{font-size:14px;line-height:1.6;margin:0 0 11px;color:var(--ink);max-width:40em;}
    .para.muted{color:var(--muted);}
    .bullets{margin:6px 0 0;padding-left:0;list-style:none;}
    .bullets li{font-size:14px;line-height:1.6;margin:0 0 8px;padding-left:20px;position:relative;color:var(--ink);}
    .bullets li:before{content:"";position:absolute;left:2px;top:9px;width:7px;height:7px;border-radius:50%;background:var(--blue);}
    .unavailable{display:flex;align-items:center;gap:10px;border:1px solid var(--border);
      padding:14px 16px;color:var(--muted);font-size:13px;margin-top:6px;}
    .ua-icon{display:inline-flex;align-items:center;justify-content:center;width:22px;height:22px;
      border:1px solid var(--border);font-weight:700;color:var(--muted);}

    /* ── Cover (unchanged brand motifs) ── */
    .cover{height:297mm;position:relative;overflow:hidden;}
    /* Wave accent band: a full-height dark strip down the RIGHT edge, sitting
       BELOW the top logo row and behind all cover text. */
    .cv-wave{position:absolute;top:34mm;right:0;bottom:0;width:46mm;
      object-fit:cover;object-position:left center;z-index:0;}
    .cover.has-wave .cv-top{right:52mm;}   /* keep the InfyApp logo clear of the band */
    .cover.has-wave .cv-arrow{display:none;} /* arrow would fall on the dark band */
    .cv-top{position:absolute;top:8mm;left:16mm;right:16mm;display:flex;align-items:center;justify-content:space-between;z-index:1;}
    .cv-client-logo{max-height:150px;max-width:320px;object-fit:contain;display:block;}
    .cv-logo{height:150px;display:block;}
    .cv-title-wrap{position:absolute;left:16mm;top:460px;}
    .cv-title{font-size:72px;line-height:1.0;margin:0;font-weight:600;color:var(--ink);letter-spacing:-.02em;}
    .cv-seo{color:var(--heading-accent);}
    .cv-sub{font-size:32px;color:var(--ink);margin-top:6px;font-weight:400;}
    .cv-client-wrap{position:absolute;left:16mm;top:690px;}
    .cv-label{font-size:13px;color:var(--muted);margin-bottom:2px;}
    .cv-client{font-size:24px;font-weight:600;color:var(--ink);}
    .cv-domain{font-size:14px;color:var(--muted);margin-top:2px;}
    .cv-period{position:absolute;left:16mm;top:800px;}
    .cv-period-val{font-size:16px;color:var(--ink);}
    .cv-prep{position:absolute;left:16mm;bottom:40px;}
    .cv-prep-name{font-size:16px;font-weight:600;color:var(--ink);}
    .cv-arrow{position:absolute;right:40px;bottom:44px;width:54px;}
    .cv-ellipses,.cv-dots{display:none;}

    /* ── Blueprint crop-marks (the "+" at card corners) ── */
    .bp{position:relative;border:1px solid var(--border);}
    .bp::before,.bp::after{content:"";position:absolute;width:9px;height:9px;color:var(--muted);
      background:linear-gradient(currentColor,currentColor) center/1px 9px no-repeat,
                 linear-gradient(currentColor,currentColor) center/9px 1px no-repeat;opacity:.65;}
    .bp::before{top:-5px;left:-5px;}
    .bp::after{bottom:-5px;right:-5px;}

    /* ── Metric grid (blueprint cells) ── */
    .grid{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:10px;
      border:1px solid var(--border);}
    .card{background:none;border:1px solid var(--border);margin:-1px 0 0 -1px;padding:14px 16px;position:relative;}
    .card-label{font-size:10px;color:var(--blue);text-transform:uppercase;letter-spacing:.1em;font-weight:700;}
    .card-value{font-family:'Barlow Condensed',Arial,sans-serif;font-size:28px;font-weight:600;margin:4px 0 3px;color:var(--ink);line-height:1.08;}
    .card-row{display:flex;gap:10px;align-items:baseline;font-size:11px;}
    .prev{color:var(--muted);}
    .delta{font-weight:600;} .delta.up{color:var(--green);} .delta.down{color:var(--red);} .delta.flat{color:var(--muted);}

    /* ── Data tables (industry .table) ── */
    table.dt{width:100%;border-collapse:collapse;margin-top:10px;font-size:13.5px;}
    table.dt th{background:none;color:var(--muted);text-align:left;font-weight:700;
      padding:7px 8px;border-bottom:1px solid var(--border);font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;}
    table.dt td{padding:9px 8px;border-bottom:1px solid rgba(29,31,32,.08);color:var(--ink);}
    table.dt th.num,table.dt td.num{text-align:right;font-variant-numeric:tabular-nums;}
    table.dt td.empty{text-align:center;color:var(--muted);padding:18px;}
    table.kw{font-size:13px;}
    table.kw th,table.kw td{border:1px solid var(--border);text-align:center;padding:7px 8px;}
    table.kw td:first-child{text-align:left;}
    table.kw th{background:none;color:var(--muted);text-transform:uppercase;font-size:10.5px;letter-spacing:.06em;}
    table.kw tbody tr.row-up{background:rgba(22,163,74,.14);}
    table.kw tbody tr.row-down{background:rgba(220,38,38,.12);}
    .legend{display:flex;gap:14px;margin:8px 0 0;font-size:11px;}
    .legend .lg{display:inline-flex;align-items:center;gap:5px;color:var(--muted);}

    /* ── Backlinks / posts list ── */
    ol.backlinks{list-style:none;margin:10px 0 0;padding:0;}
    ol.backlinks li{display:flex;align-items:baseline;gap:12px;padding:7px 0;
      border-bottom:1px solid rgba(29,31,32,.08);font-size:12.5px;}
    .bl-n{flex:0 0 26px;color:var(--blue);font-weight:600;text-align:right;font-variant-numeric:tabular-nums;}
    .bl-url{word-break:break-all;color:var(--ink);}

    /* ── Chart card (blueprint) ── */
    .chart-card{border:1px solid var(--border);padding:16px 18px;margin-top:10px;position:relative;}
    .chart-kicker{font-size:10px;letter-spacing:.1em;text-transform:uppercase;color:var(--blue);margin-bottom:6px;}
    .chart-legend{display:flex;gap:16px;margin:0 0 6px;font-size:12px;color:var(--muted);}
    .chart-legend .lg{display:inline-flex;align-items:center;gap:6px;}
    .chart-legend .lg i{width:14px;height:3px;border-radius:0;display:inline-block;}
    svg.chart{width:100%;height:auto;}
    svg.chart .gl{stroke:var(--border);stroke-width:1;}
    svg.chart .yl{fill:var(--muted);font-size:10px;text-anchor:end;}
    svg.chart .xl{fill:var(--muted);font-size:10px;}

    /* ── TOC ── */
    .toc-hero-img{display:block;width:100%;height:150px;object-fit:cover;margin-bottom:26px;}
    .toc-hero{height:120px;margin-bottom:26px;display:flex;align-items:center;justify-content:center;
      border:1px solid var(--border);}
    .toc-seo{font-family:'Barlow Condensed',sans-serif;font-size:44px;font-weight:600;color:var(--heading-accent);letter-spacing:.02em;}
    .toc-cols{display:grid;grid-template-columns:1fr 1fr;gap:34px;margin-top:14px;}
    .toc-row{display:flex;gap:14px;align-items:baseline;margin-bottom:16px;}
    .toc-n{font-family:'Barlow Condensed',sans-serif;font-size:18px;font-weight:600;color:var(--blue);min-width:30px;}
    .toc-t{font-size:15px;color:var(--ink);}

    /* ── Banner (maturing notice) → plain italic like industry ── */
    .banner{color:var(--muted);font-style:italic;font-size:12.5px;margin-bottom:16px;max-width:40em;}

    /* ── Content-page header (dual logo slots + centered title) ── */
    .rpt-header{position:absolute;top:0;left:0;right:0;height:22mm;padding:0 16mm;
      display:flex;align-items:center;justify-content:space-between;border-bottom:1px solid var(--border);}
    .rh-logo{width:130px;height:44px;display:flex;align-items:center;
      justify-content:center;color:var(--neutral,#b7b7ba);font-size:10px;letter-spacing:.14em;
      font-family:'Barlow Condensed',Arial,sans-serif;overflow:hidden;}
    .rh-empty{visibility:hidden;}
    .rh-logo img{max-width:100%;max-height:100%;object-fit:contain;}
    .rh-title{flex:1;text-align:center;font-family:'Barlow Condensed',Arial,sans-serif;font-weight:600;
      color:var(--blue);font-size:12px;letter-spacing:.16em;text-transform:uppercase;}

    /* ── Footer (two tiers) ── */
    .footer{position:absolute;bottom:0;left:0;right:0;padding:0 16mm 7mm;}
    .ft-main{display:flex;justify-content:space-between;align-items:center;gap:16px;
      border-top:1px solid var(--border);padding-top:8px;font-family:'Barlow',Arial,sans-serif;font-size:10px;color:var(--ga);}
    .ft-sub{display:flex;justify-content:space-between;margin-top:5px;font-family:'Barlow',Arial,sans-serif;
      font-size:9px;color:#b7b7ba;letter-spacing:.02em;}
    .ft-sub .ft-pg{font-variant-numeric:tabular-nums;}

    /* ── Thank you ── */
    .thankyou{height:297mm;}
    .ty-logo{position:absolute;top:16mm;left:16mm;z-index:2;}
    .ty-logo img{height:110px;display:block;}
    .ty-dots-tr,.ty-dots-bl{display:none;}
    .ty-body{position:absolute;left:16mm;top:300px;max-width:380px;z-index:2;}
    .ty-title{font-family:'Barlow Condensed',sans-serif;font-size:56px;font-weight:600;color:var(--ink);margin:0 0 22px;letter-spacing:-.02em;}
    .ty-p{font-size:17px;line-height:1.6;color:var(--ga);margin:0;}
    .ty-contact{position:absolute;right:16mm;bottom:120px;font-size:15px;color:var(--ink);line-height:2.1;z-index:2;}
    /* Delta arrows drawn with borders — no font glyph, so they survive any host. */
    .tri{display:inline-block;width:0;height:0;vertical-align:middle;margin-right:5px;
      border-left:4px solid transparent;border-right:4px solid transparent;}
    .tri.t-up{border-bottom:6px solid currentColor;}
    .tri.t-down{border-top:6px solid currentColor;}
    .ty-contact>div{display:flex;align-items:center;gap:10px;}
    .ty-contact .ci{color:var(--blue);flex:none;display:block;}

    /* -- Previous vs current comparison -- */
    .cmp-grid{display:grid;grid-template-columns:1fr 1fr;gap:40px;margin-top:8px;}
    .cmp-head{color:var(--blue);font-family:'Barlow Condensed',sans-serif;font-size:20px;font-weight:600;margin:0 0 14px;}
    .cmp-metric{margin-bottom:14px;}
    .cmp-l{font-size:11px;color:var(--blue);text-transform:uppercase;letter-spacing:.08em;font-weight:700;margin-bottom:1px;}
    .cmp-v{font-family:'Barlow Condensed',sans-serif;font-size:26px;font-weight:600;color:var(--ink);line-height:1.08;}

    /* -- Targets & Goals grid -- */
    .tg-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:16px 20px;margin:8px 0 4px;}
    .tg-cell{margin-bottom:8px;}
    .tg-l{font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px;}
    .tg-v{font-family:'Barlow Condensed',sans-serif;font-size:24px;font-weight:600;color:var(--blue);}
    .tg-divider{height:1px;background:var(--border);margin:16px 0 20px;}
    .col-head{font-family:'Barlow Condensed',sans-serif;font-size:18px;color:var(--ink);margin:0 0 10px;}

.grid>.card::before,.grid>.card::after,.chart-card::before,.chart-card::after{
      content:"";position:absolute;width:9px;height:9px;color:var(--muted);opacity:.55;
      background:linear-gradient(currentColor,currentColor) center/1px 9px no-repeat,
                linear-gradient(currentColor,currentColor) center/9px 1px no-repeat;}
    .grid>.card::before,.chart-card::before{top:-5px;left:-5px;}
    .grid>.card::after,.chart-card::after{bottom:-5px;right:-5px;}
    @media print{ @page{size:A4;margin:0;} }
    """
    imports = "@import url('https://fonts.googleapis.com/css2?family=Barlow:ital,wght@0,400;0,500;1,400&family=Barlow+Condensed:wght@600;700&display=swap');"
    return imports + _font_face_css() + vars_css + body_css


def _targets_grid_page(block: dict) -> str:
    title = block.get("title") or ""
    columns = block.get("columns") or []
    fields = block.get("fields") or []
    values = block.get("values") or {}

    def cell(col_key, f):
        raw = (values.get(col_key) or {}).get(f.get("key"))
        shown = _esc(raw) if raw not in (None, "") else "&mdash;"
        return (f'<div class="tg-cell"><div class="tg-l">{_esc(f.get("label"))}</div>'
                f'<div class="tg-v">{shown}</div></div>')

    groups = []
    for i, col in enumerate(columns):
        grid = "".join(cell(col.get("key"), f) for f in fields)
        divider = '<div class="tg-divider"></div>' if i < len(columns) - 1 else ""
        groups.append(f'<h3 class="col-head">{_esc(col.get("label"))}</h3>'
                      f'<div class="tg-grid">{grid}</div>{divider}')

    notes = block.get("notes")
    notes_html = f'<p class="para" style="margin-top:18px">{_esc(notes)}</p>' if notes else ""
    return _section_head(title) + "".join(groups) + notes_html


def _thead_title(title: str) -> str:
    if not (title or "").strip():
        return ""
    return f'<h2 class="section tbl-h">{_esc(title)}</h2>'


def _narrative_is_empty(b: dict) -> bool:
    doc = b.get("doc")
    if isinstance(doc, dict) and doc.get("type") == "doc":
        def has_text(nodes):
            for n in nodes or []:
                t = n.get("type")
                if t == "text" and (n.get("text") or "").strip():
                    return True
                if t == "blob":
                    return True
                if has_text(n.get("content")):
                    return True
            return False
        if has_text(doc.get("content")):
            return False
    return not ((b.get("paragraphs") or []) or (b.get("bullets") or []))


def _data_table_inline(b: dict) -> str:
    title = b.get("title") or ""
    columns = b.get("columns") or []
    head = _section_head(title) if b.get("id") == "keywords" else _thead_title(title)
    if b.get("available") is False:
        return head + _unavailable(b.get("unavailableReason"))
    all_rows = b.get("rows") or []
    rows = [r for r in all_rows if _included(r)]
    head_cells = "".join(
        f'<th class="{ "num" if c.get("kind") in ("metric","delta") else "" }">{_esc(c.get("label"))}</th>'
        for c in columns)
    thead = f"<thead><tr>{head_cells}</tr></thead>"
    is_kw = b.get("id") == "keywords"
    cls = "dt kw" if is_kw else "dt"
    if not rows:
        msg = "No rows selected for this period." if all_rows else "No rows for this period."
        body = f'<tr><td colspan="{len(columns)}" class="empty">{_esc(msg)}</td></tr>'
        return head + f'<table class="{cls}">{thead}<tbody>{body}</tbody></table>'
    body_rows = []
    for r in rows:
        cells = (r or {}).get("cells") or {}
        tone = ""
        if is_kw:
            d = cells.get("rank_delta")
            tone = "row-up" if (_num(d) and d < 0) else ("row-down" if (_num(d) and d > 0) else "")
        tds = "".join(_table_cell_html(c, cells.get(c.get("key"))) for c in columns)
        body_rows.append(f'<tr class="{tone}">{tds}</tr>' if is_kw else f"<tr>{tds}</tr>")
    return head + f'<table class="{cls}">{thead}<tbody>{"".join(body_rows)}</tbody></table>'


def _render_block_inline(b: dict, vs_sub: str, blobs_by_name, period_label='', prev_label='') -> str:
    t = b.get("type")
    if t == "narrative":
        return "" if _narrative_is_empty(b) else _narrative_page(b, "", blobs_by_name)
    if t == "metric_grid":
        return _metric_grid_page(b, vs_sub, period_label, prev_label)
    if t == "chart":
        return _chart_page(b)
    if t == "targets_grid":
        return _targets_grid_page(b)
    if t == "data_table":
        return _data_table_inline(b)
    return ""


_PAGE_GROUPS = [
    ("Progress Summary", ["progress-summary"],True),
    ("Key Metrics", ["key-metrics", "achievements"], False),
    ("Domain Authority & Backlinks (Moz)", ["moz-overview"], False),
    ("GA4 - Audience Overview", ["ga4-overview-notes", "ga4-overview", "ga4-users-trend", "ga4-graph-notes"], True),
    ("Traffic by Channel", ["ga4-by_channel"], False),
    ("Users by Country & City", ["ga4-cities-notes", "ga4-by_country_city"], False),
    ("Top Landing Pages", ["ga4-landing-notes", "ga4-by_landing_page"], False),
    ("Detailed Traffic Summary", ["ga4-by_device", "ga4-by_browser", "ga4-by_operating_system", "ga4-by_language"], True),
    ("Search Console", ["gsc-notes", "gsc-overview", "gsc-trend"], True),
    ("Keyword Rankings", ["keywords"], True),
    ("New Backlinks", ["backlinks"], True),
    ("Blog Posts", ["posts-blogs"], True),
    ("LinkedIn Posts", ["posts-linkedin"], True),
    ("Targets & Goals", ["targets", "targets-notes"], True),
    ("Strategy & Notes", ["strategy"], True),
]


def _doc_text_len(doc) -> int:
    total = 0
    def walk(nodes):
        nonlocal total
        for n in nodes or []:
            if n.get("type") == "text":
                total += len(n.get("text") or "")
            walk(n.get("content"))
    walk((doc or {}).get("content"))
    return total


def _node_text_len(node) -> int:
    total = 0
    stack = [node]
    while stack:
        nd = stack.pop()
        if nd.get("type") == "text":
            total += len(nd.get("text") or "")
        stack.extend(nd.get("content") or [])
    return total


def _doc_para_lens(doc) -> list:
    lens = []
    for node in (doc or {}).get("content") or []:
        t = node.get("type")
        if t in ("bulletList", "orderedList"):
            for li in node.get("content") or []:
                lens.append(_node_text_len(li))
        else:
            lens.append(_node_text_len(node))
    return lens


def _block_units(b: dict) -> float:
    t = b.get("type")
    if t == "narrative":
        if _narrative_is_empty(b):
            return 0.0
        import math as _m
        doc = b.get("doc")
        if isinstance(doc, dict) and doc.get("type") == "doc":
            lens = _doc_para_lens(doc)
        else:
            lens = ([len(x) for x in (b.get("paragraphs") or [])]
                    + [len(x) for x in (b.get("bullets") or [])])
        if not lens:
            lens = [0]
        text_px = sum(_m.ceil(max(1, l / 90)) * 23 + 14 for l in lens)
        head = 50 if b.get("title") else 0
        return head + text_px + 24
    if t == "metric_grid":
        n = len(b.get("metrics") or [])
        return 104 + n * 58
    if t == "chart":
        return 380
    if t == "data_table":
        rows = len([r for r in (b.get("rows") or []) if _included(r)])
        return 89 + rows * 28
    if t == "targets_grid":
        return 454
    return 40


_PAGE_BUDGET = 940.0

_BREAK_BEFORE = {"GA4 - Audience Overview", "Detailed Traffic Summary", "Search Console", "Targets & Goals", "Strategy & Notes"}

_KEEP_TOGETHER = {"Targets & Goals"}


def _build_section_pages(content: dict, period_label: str, prev_label: str, blobs_by_name=None):
    header = _header_block(content)
    maturing = header.get("maturingNotice") if header.get("maturing") else None
    banner = f'<div class="banner">{_esc(maturing)}</div>' if maturing else ""
    vs_sub = (f"Current period vs. previous ({_esc(prev_label)})"
              if prev_label else "Current period vs. previous period")

    blocks = [b for b in _blocks(content) if b.get("type") != "report_header"]
    id_to_group = {}
    for gi, (_t, ids, _s) in enumerate(_PAGE_GROUPS):
        for bid in ids:
            id_to_group[bid] = gi
    grouped = [[] for _ in _PAGE_GROUPS]
    current = 0
    for b in blocks:
        gi = id_to_group.get(b.get("id"))
        if gi is None:
            grouped[current].append(b)
        else:
            current = gi
            grouped[gi].append(b)

    BIG = _PAGE_BUDGET + 1.0
    items = []
    section_no = 0
    for gi, (title, _ids, show_title) in enumerate(_PAGE_GROUPS):
        gblocks = grouped[gi]
        if not gblocks:
            continue
        section_no += 1
        eyebrow = f'<div class="rp-eyebrow">Section {section_no:02d}</div>'
        state = {"started": False}
        rep = title
        if not show_title:
            for _pb in gblocks:
                if str(_pb.get("id") or "").endswith("-notes"):
                    continue
                _pt = (_pb.get("title") or "").strip()
                if _pt:
                    rep = _pt
                break

        if title in _KEEP_TOGETHER:
            parts = [eyebrow]
            if show_title:
                parts.append(f'<div class="blk"><h2 class="section">{_esc(title)}</h2></div>')
            for b in gblocks:
                html = _render_block_inline(b, vs_sub, blobs_by_name, period_label, prev_label)
                if html:
                    parts.append(f'<div class="blk">{html}</div>')
            if parts:
                items.append((rep, "".join(parts), "flow", True, 200.0))
            continue

        def mark():
            first = not state["started"]
            state["started"] = True
            return first

        pend = (f'<div class="blk">{eyebrow}<h2 class="section">{_esc(title)}</h2></div>'
                if show_title else eyebrow)
        pend_u = 90.0 if show_title else 24.0
        for b in gblocks:
            t = b.get("type")
            if t == "backlinks_list":
                for inner in _backlinks_pages(b, extra_head_px=pend_u):
                    items.append((rep, pend + inner, "page", mark(), BIG))
                    pend, pend_u = "", 0.0
                continue
            if t == "data_table":
                rws = [r for r in (b.get("rows") or []) if _included(r)]
                cap = _KEYWORD_ROWS_PER_PAGE if b.get("id") == "keywords" else _TABLE_ROWS_PER_PAGE
                if len(rws) > cap:
                    inner_pages = (_keyword_pages(b) if b.get("id") == "keywords"
                                   else _data_table_pages(b, "", _TABLE_ROWS_PER_PAGE))
                    for inner in inner_pages:
                        items.append((rep, pend + inner, "page", mark(), BIG))
                        pend, pend_u = "", 0.0
                    continue
            html = _render_block_inline(b, vs_sub, blobs_by_name, period_label, prev_label)
            if not html:
                continue
            items.append((rep, pend + f'<div class="blk">{html}</div>', "flow", mark(), pend_u + _block_units(b)))
            pend, pend_u = "", 0.0

    pages = []
    cur, cur_units, cur_starts = [], 0.0, []

    def flush():
        nonlocal cur, cur_units, cur_starts
        if cur:
            pages.append({"html": "".join(cur), "starts": cur_starts})
        cur, cur_units, cur_starts = [], 0.0, []

    for (title, html, kind, is_start, units) in items:
        force_break = is_start and title in _BREAK_BEFORE
        if kind == "page":
            flush()
            pages.append({"html": html, "starts": [title] if is_start else []})
            continue
        if cur and (force_break or cur_units + units > _PAGE_BUDGET):
            flush()
        if is_start:
            cur_starts.append(title)
        cur.append(html)
        cur_units += units
    flush()

    if banner and pages:
        pages[0]["html"] = banner + pages[0]["html"]
    return pages


def render_html(version: dict, blobs: list | None = None) -> str:
    content = version.get("content") or {}
    header = _header_block(content)
    period_label = (content.get("period_label") or header.get("periodLabel")
                    or version.get("periodKey") or "")
    prev_label = content.get("prev_period_label") or header.get("prevPeriodLabel") or ""
    period_key = content.get("period_key") or version.get("periodKey") or ""
    period_range = _period_range_label(period_key, period_label)

    blobs_by_name = {b.get("name"): b for b in (blobs or [])}
    section_pages = _build_section_pages(content, period_label, prev_label, blobs_by_name)

    content_start = 3
    toc_entries = []
    seen = set()
    for i, pg in enumerate(section_pages):
        page_no = content_start + i
        for title in pg["starts"]:
            if title not in seen:
                seen.add(title)
                toc_entries.append((title, page_no))

    total_pages = 2 + len(section_pages) + 1

    project_name = header.get("projectName") or (content.get("project") or {}).get("name") or ""
    domain = header.get("domain") or (content.get("project") or {}).get("domain") or ""
    parts = [_cover_html(header, period_label, period_range),
             _toc_html(toc_entries, period_range, 2, total_pages)]
    for i, pg in enumerate(section_pages):
        parts.append(_wrap_content_page(pg["html"], period_range, content_start + i, total_pages,
                                        project_name=project_name, domain=domain,
                                        client_logo=header.get("clientLogo") or ""))
    parts.append(_thankyou_html())

    return (f'<!doctype html><html><head><meta charset="utf-8">'
            f'<style>{_css()}</style></head><body>{"".join(parts)}</body></html>')


def render_pdf(version: dict, blobs: list | None = None) -> bytes:
    from playwright.sync_api import sync_playwright

    parts = None
    agency = ""
    try:
        from . import report_industry
        parts = {pt: report_industry.render_document(version, blobs, part=pt)
                 for pt in ("cover", "content", "thankyou")}
        agency = report_industry._agency_logo()
    except Exception as exc:
        print('industry renderer failed, using legacy:', exc)
        html_str = render_html(version, blobs)

    logo_img = f'<img src="{agency}" style="height:9mm">' if agency else ""
    header_tpl = (
        '<div style="width:100%;box-sizing:border-box;padding:0 14mm;text-align:right;'
        f'-webkit-print-color-adjust:exact;print-color-adjust:exact">{logo_img}</div>')
    _content = version.get("content") or {}
    _hdr = next((b for b in (_content.get("blocks") or []) if b.get("type") == "report_header"), {})
    _period_label = _hdr.get("periodLabel") or _content.get("period_label") or ""
    _month = _period_label.split()[0] if _period_label else ""
    if not _month:
        _MONTHS = ["", "January", "February", "March", "April", "May", "June", "July",
                   "August", "September", "October", "November", "December"]
        _pk = _hdr.get("period_key") or _content.get("period_key") or version.get("periodKey") or ""
        try:
            _month = _MONTHS[int(str(_pk).split("-")[1])]
        except Exception:
            _month = ""
    _footer_title = f"{_month} SEO Report" if _month else "Monthly SEO Report"
    footer_tpl = (
        '<div style="width:100%;box-sizing:border-box;font-size:10px;color:#5d5d60;padding:0 14mm;'
        'display:flex;align-items:center;justify-content:space-between;'
        '-webkit-print-color-adjust:exact;print-color-adjust:exact">'
        f'<span>{_esc(_footer_title)}</span>'
        '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            def _to_pdf(html, **kw):
                page = browser.new_page()
                page.set_content(html, wait_until="networkidle")
                try:
                    page.evaluate("() => document.fonts && document.fonts.ready")
                except Exception:
                    pass
                page.emulate_media(media="print")
                data = page.pdf(**kw)
                page.close()
                return data

            full_bleed = dict(format="A4", print_background=True, prefer_css_page_size=True,
                              margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
            if parts is not None:
                pdfs = [
                    _to_pdf(parts["cover"], **full_bleed),
                    _to_pdf(parts["content"], format="A4", print_background=True,
                            display_header_footer=True, header_template=header_tpl,
                            footer_template=footer_tpl,
                            margin={"top": "24mm", "bottom": "14mm", "left": "14mm", "right": "14mm"}),
                    _to_pdf(parts["thankyou"], **full_bleed),
                ]
            else:
                pdfs = [_to_pdf(html_str, **full_bleed)]
        finally:
            browser.close()

    if len(pdfs) == 1:
        return pdfs[0]
    import io
    from pypdf import PdfReader, PdfWriter
    writer = PdfWriter()
    for data in pdfs:
        for pg in PdfReader(io.BytesIO(data)).pages:
            writer.add_page(pg)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def pdf_filename(version: dict) -> str:
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

def render_cover_png(version: dict, blobs: list | None = None, width: int = 440) -> bytes:
    from playwright.sync_api import sync_playwright
    from . import report_industry

    html = report_industry.render_document(version, blobs, part="cover")

    A4_W, A4_H = 794, 1123
    scale = width / A4_W

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page(
                viewport={"width": A4_W, "height": A4_H},
                device_scale_factor=scale,
            )
            page.set_content(html, wait_until="networkidle")
            return page.screenshot(type="png")
        finally:
            browser.close()
