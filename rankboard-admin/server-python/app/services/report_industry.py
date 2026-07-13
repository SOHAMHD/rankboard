"""INDUSTRY REPORT RENDERER — produces the EXACT design the client authored
(reports/industry-print.html + ds-industry.css + doc-page.js + image-slot.js),
with the project's live data injected. This is a straight port of the client's
template: same markup, same classes, same SVG chart geometry — only the numbers,
tables and chart data change.

render(version, blobs) -> full HTML string (Playwright turns it into the PDF).
The three charts are recomputed from live data into the template's exact SVG
shapes: daily-users grouped BARS, the Search-Console clicks/impressions LINE,
and the Traffic-by-Channel DONUT.
"""
import os
from html import escape as _e

_ASSETS = os.path.join(os.path.dirname(__file__), "..", "assets", "report_design")


def _asset(name: str) -> str:
    try:
        with open(os.path.join(_ASSETS, name), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def _included(x):
    return (x or {}).get("included", True) is not False


def esc(v) -> str:
    return _e("" if v is None else str(v))


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ── charts (exact template SVG geometry, plotted from data) ──────────────────
def bar_chart(points, active_key="activeUsers", new_key="newUsers", month_label="") -> str:
    """Grouped daily bars — light (#b5d9fd active) + dark (#416180 new), matching
    the template's 680×272 viewBox, 40px left axis, 4-step gridlines."""
    n = len(points) or 1
    W, H = 680, 272
    x0, xr, yt, yb = 40, 666, 16, 228
    plot_w, plot_h = xr - x0, yb - yt
    vals = [v for p in points for v in (_num(p.get(active_key)), _num(p.get(new_key))) if v is not None]
    vmax = max(vals) if vals else 1
    # round vmax up to a "nice" top so gridline labels are clean
    import math
    top = max(5, int(math.ceil(vmax / 5.0) * 5))
    def y(v): return yb - plot_h * (v / top)
    parts = []
    # gridlines + y labels (0, 1/4, 1/2, 3/4, top)
    for g in range(4):
        gy = yb - plot_h * g / 4
        stroke = "#7a7a7d" if g == 0 else "#cfcfd2"
        parts.append(f'<line x1="{x0}" y1="{gy:.1f}" x2="{xr}" y2="{gy:.1f}" stroke="{stroke}" stroke-width="1"/>')
        parts.append(f'<text x="{x0-8:.1f}" y="{gy+3.5:.1f}" text-anchor="end" font-size="10" fill="#5d5d60" font-family="Barlow, sans-serif">{int(round(top*g/4))}</text>')
    parts.append(f'<line x1="{x0}" y1="{yt}" x2="{x0}" y2="{yb}" stroke="#7a7a7d" stroke-width="1"/>')
    slot = plot_w / n
    bw = min(16.0, slot / 3.2)
    for i, p in enumerate(points):
        cx = x0 + slot * i + slot / 2
        a = _num(p.get(active_key)) or 0
        nw = _num(p.get(new_key)) or 0
        parts.append(f'<rect x="{cx-bw-1:.1f}" y="{y(a):.1f}" width="{bw:.1f}" height="{yb-y(a):.1f}" fill="#b5d9fd"/>')
        parts.append(f'<rect x="{cx+1:.1f}" y="{y(nw):.1f}" width="{bw:.1f}" height="{yb-y(nw):.1f}" fill="#416180"/>')
        lbl = esc(p.get("label") or (i + 1))
        parts.append(f'<text x="{cx:.1f}" y="246" text-anchor="middle" font-size="10" fill="#5d5d60" font-family="Barlow, sans-serif">{lbl}</text>')
    parts.append(f'<text transform="rotate(-90 13 122)" x="13" y="122" text-anchor="middle" font-size="10" fill="#5d5d60" font-family="Barlow, sans-serif">Users</text>')
    if month_label:
        parts.append(f'<text x="353" y="268" text-anchor="middle" font-size="10" fill="#5d5d60" font-family="Barlow, sans-serif">{esc(month_label)}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:680px;display:block" role="img" aria-label="Daily users">'
            + "".join(parts) + "</svg>")


def donut(slices, total_label="") -> str:
    """stroke-dasharray donut on r=79, stroke-width 32 (circumference ≈ 496.37),
    palette #597ea3/#94bce3/#98989b/#d4d4d7, matching the template."""
    palette = ["#597ea3", "#94bce3", "#98989b", "#d4d4d7", "#749dc4", "#416180"]
    C = 2 * 3.141592653589793 * 79
    total = sum(max(0, _num(s.get("value")) or 0) for s in slices) or 1
    segs = []
    offset = 0.0
    for i, s in enumerate(slices):
        val = max(0, _num(s.get("value")) or 0)
        length = C * (val / total)
        col = palette[i % len(palette)]
        segs.append(f'<circle cx="95" cy="95" r="79" fill="none" stroke="{col}" stroke-width="32" '
                    f'stroke-dasharray="{length:.2f} {C-length:.2f}" stroke-dashoffset="{-offset:.2f}" '
                    f'transform="rotate(-90 95 95)"/>')
        offset += length
    center = esc(int(total)) if total_label else ""
    return (f'<svg viewBox="0 0 190 190" width="190" height="190" role="img" aria-label="Traffic by channel">'
            + "".join(segs)
            + f'<text x="95" y="93" text-anchor="middle" font-size="26" font-family="\'Barlow Condensed\',sans-serif" font-weight="600" fill="#1d1f20">{center}</text>'
            + f'<text x="95" y="112" text-anchor="middle" font-size="10" font-family="Barlow,sans-serif" fill="#5d5d60">{esc(total_label)}</text>'
            + "</svg>")


def card(kicker="", title="", meta="", body="", title_size=24) -> str:
    inner = '<i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>'
    if kicker:
        inner += f'<div class="card-kicker">{esc(kicker)}</div>'
    if title != "":
        inner += f'<div class="card-title" style="font-size:{title_size}px">{esc(title)}</div>'
    if meta:
        inner += f'<div class="card-meta">{esc(meta)}</div>'
    if body:
        inner += f'<p class="card-body">{esc(body)}</p>'
    return f'<div class="card blueprint">{inner}</div>'


def table(headers, rows) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{esc(c)}</td>" for c in r) + "</tr>" for r in rows)
    return f'<table class="table"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def section(n: int, title: str, break_before: bool = False) -> str:
    lead = ('<div style="break-before:page;height:10px"></div>' if break_before
            else '<div style="height:56px"></div>')
    return (lead
            + f'<h6 style="color:var(--color-accent);margin-bottom:8px">Section {n:02d}</h6>'
            + f'<h2 style="margin-bottom:var(--space-4)">{esc(title)}</h2>')


# ── data helpers over the report_document blocks ─────────────────────────────
def _blocks(content):
    return (content or {}).get("blocks") or []


def _by_id(content):
    return {b.get("id"): b for b in _blocks(content)}


def _para(block):
    if not block:
        return ""
    return " ".join(p for p in (block.get("paragraphs") or []) if p)



def _inline(nodes):
    out = []
    for nd in nodes or []:
        t = nd.get("type")
        if t == "text":
            txt = esc(nd.get("text") or "")
            for m in nd.get("marks") or []:
                mt = m.get("type")
                if mt == "bold":
                    txt = f"<strong>{txt}</strong>"
                elif mt == "italic":
                    txt = f"<em>{txt}</em>"
            out.append(txt)
        elif t == "hardBreak":
            out.append("<br>")
        elif nd.get("content"):
            out.append(_inline(nd.get("content")))
    return "".join(out)


def _doc_html(doc):
    """Render a TipTap doc (what the editor stores) to HTML — paragraphs,
    bullet/ordered lists, bold/italic. This is the edited content."""
    if not isinstance(doc, dict):
        return ""
    html = []
    for nd in doc.get("content") or []:
        t = nd.get("type")
        if t == "paragraph":
            inner = _inline(nd.get("content"))
            if inner.strip():
                html.append(f"<p>{inner}</p>")
        elif t in ("bulletList", "orderedList"):
            tag = "ol" if t == "orderedList" else "ul"
            lis = []
            for li in nd.get("content") or []:
                kids = li.get("content") or []
                inner = _inline((kids[0].get("content") if kids else None))
                lis.append(f"<li>{inner}</li>")
            html.append(f"<{tag}>{''.join(lis)}</{tag}>")
        elif t == "heading":
            html.append(f"<h4>{_inline(nd.get('content'))}</h4>")
    return "".join(html)


def _rich(block):
    """Edited rich text if present (TipTap doc), else the legacy paragraphs/bullets."""
    if not block:
        return ""
    doc = block.get("doc")
    if isinstance(doc, dict) and doc.get("content"):
        h = _doc_html(doc)
        if h.strip():
            return h
    out = "".join(f"<p>{esc(p)}</p>" for p in (block.get("paragraphs") or []) if p)
    bl = block.get("bullets") or []
    if bl:
        out += "<ul>" + "".join(f"<li>{esc(b)}</li>" for b in bl) + "</ul>"
    return out


def _list_items(block):
    """Extract (title, body) pairs from a rich block's list items — the bold
    lead becomes the card title, the rest the body."""
    doc = (block or {}).get("doc")
    pairs = []
    if isinstance(doc, dict):
        for nd in doc.get("content") or []:
            if nd.get("type") in ("bulletList", "orderedList"):
                for li in nd.get("content") or []:
                    kids = li.get("content") or []
                    spans = (kids[0].get("content") if kids else None) or []
                    title, rest = "", ""
                    for sp in spans:
                        txt = sp.get("text") or ""
                        if any(m.get("type") == "bold" for m in sp.get("marks") or []):
                            title += txt
                        else:
                            rest += txt
                    title = title.strip().rstrip(":").strip()
                    rest = rest.strip().lstrip(":").strip()
                    if title or rest:
                        pairs.append((title or "Highlight", rest))
    if not pairs:
        for b in (block or {}).get("bullets") or []:
            if ":" in b:
                t, r = b.split(":", 1)
                pairs.append((t.strip(), r.strip()))
            else:
                pairs.append(("Highlight", b))
    return pairs


def _fmt(type_, val):
    from . import report_pdf
    try:
        return report_pdf._fmt_value(type_, val)
    except Exception:
        return "" if val is None else str(val)


def _metric_cards(block, prev_label="Prev"):
    if not block:
        return ""
    out = []
    for m in block.get("metrics") or []:
        cur = _fmt(m.get("type"), m.get("currentValue"))
        prev = m.get("previousValue")
        meta = f"{prev_label}: {_fmt(m.get('type'), prev)}" if prev is not None else ""
        out.append(card(kicker=m.get("label"), title=cur, meta=meta))
    return "".join(out)


def _table_block(block):
    if not block or not block.get("columns"):
        return ""
    cols = block.get("columns")
    headers = [c.get("label") for c in cols]
    rows = []
    for r in (block.get("rows") or []):
        if not _included(r):
            continue
        cells = r.get("cells") or {}
        row = []
        for c in cols:
            v = cells.get(c.get("key"))
            row.append(v if c.get("kind") == "dim" else _fmt(c.get("type"), v))
        rows.append(row)
    return table(headers, rows)


def _chart_points(block):
    return (block or {}).get("points") or []


def render_document(version, blobs=None) -> str:
    from . import report_pdf
    content = version.get("content") or {}
    bid = _by_id(content)
    header = bid.get("header") or next((b for b in _blocks(content) if b.get("type") == "report_header"), {})
    project = header.get("projectName") or (content.get("project") or {}).get("name") or "SEO Report"
    domain = header.get("domain") or (content.get("project") or {}).get("domain") or ""
    period_label = header.get("periodLabel") or content.get("period_label") or ""
    prev_label = header.get("prevPeriodLabel") or content.get("prev_period_label") or "Prev"
    try:
        period_range = report_pdf._period_range_label(content.get("period_key") or "", period_label)
    except Exception:
        period_range = period_label
    maturing = header.get("maturingNotice") if header.get("maturing") else ""

    def g(i):
        return bid.get(i)

    # Fixed section numbers + page-break rule from the client:
    # new page before 2,4,5,6,7,8,9,10 (1 first; 3 flows after 2; 11 flows after 10).
    body = [section(1, "Progress Summary")]
    if maturing:
        body.append(f'<p class="text-muted" style="font-style:italic;font-size:12.5px;max-width:38em">{esc(maturing)}</p>')
    if _rich(g("progress-summary")):
        body.append(f'<div style="font-size:16px;max-width:38em;margin-top:var(--space-3)">{_rich(g("progress-summary"))}</div>')
    cards = _metric_cards(g("key-metrics"), prev_label)
    if cards:
        body.append(f'<div style="margin-top:var(--space-6)"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-3)">{cards}</div></div>')
    pairs = _list_items(g("achievements"))
    if pairs:
        body.append('<h4 style="margin-top:var(--space-8)">Key achievements</h4>')
        cc = "".join(card(title=t, body=b, title_size=16) for t, b in pairs[:8])
        body.append(f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-3);margin-top:var(--space-3)">{cc}</div>')

    # 02 Audience Overview
    body.append(section(2, "Audience Overview", True))
    if _rich(g("ga4-overview-notes")):
        body.append(f'<div style="max-width:38em">{_rich(g("ga4-overview-notes"))}</div>')
    ocards = _metric_cards(g("ga4-overview"), prev_label)
    if ocards:
        body.append(f'<div style="margin-top:var(--space-4)"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--space-3)">{ocards}</div></div>')
    trend = g("ga4-users-trend")
    if trend and _chart_points(trend):
        body.append('<h4 style="margin-top:var(--space-8)">Daily active &amp; new users</h4>')
        body.append('<div style="display:flex;gap:16px;margin:8px 0 10px;font-size:11px" class="text-muted">'
                    '<span style="display:inline-flex;align-items:center;gap:5px"><i style="width:10px;height:10px;background:#b5d9fd;display:inline-block"></i>Active users</span>'
                    '<span style="display:inline-flex;align-items:center;gap:5px"><i style="width:10px;height:10px;background:#416180;display:inline-block"></i>New users</span></div>')
        pts = [{"label": (p.get("x") or "")[8:10].lstrip("0") or (i + 1), "activeUsers": p.get("activeUsers"), "newUsers": p.get("newUsers")}
               for i, p in enumerate(_chart_points(trend))]
        body.append('<div class="card blueprint" style="padding:var(--space-4)"><i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>'
                    + bar_chart(pts, month_label=period_label) + '</div>')

    # 03 Traffic by Channel — prose + legend + DONUT + table
    ch = g("ga4-by_channel")
    if ch:
        body.append(section(3, "Traffic by Channel"))
        cols = ch.get("columns") or []
        tu_key = next((c.get("key") for c in cols if c.get("key") == "totalUsers"), None) \
                 or next((c.get("key") for c in cols if c.get("kind") == "metric"), None)
        rows = [r for r in (ch.get("rows") or []) if _included(r)]
        slices = []
        for r in rows:
            cells = r.get("cells") or {}
            slices.append({"label": cells.get("dim0"), "value": _num(cells.get(tu_key)) or 0})
        total = sum(s["value"] for s in slices) or 1
        legend = "".join(
            f'<div style="display:flex;align-items:center;gap:8px;font-size:13px"><i style="width:10px;height:10px;flex:none;background:{c}"></i>'
            f'<span style="flex:1">{esc(s["label"])}</span><span class="text-muted">{round(s["value"]/total*100)}%</span></div>'
            for s, c in zip(slices, ["#597ea3", "#94bce3", "#98989b", "#d4d4d7", "#749dc4", "#416180"] * 3))
        body.append(
            '<div style="display:grid;grid-template-columns:1.1fr 1fr;gap:var(--space-6);align-items:start">'
            f'<div><div style="display:flex;flex-direction:column;gap:8px;margin-top:var(--space-3)">{legend}</div></div>'
            '<div class="card blueprint"><i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>'
            '<div class="card-kicker">Share of total users</div>'
            f'<div style="display:flex;justify-content:center;padding:var(--space-2) 0">{donut(slices, "total users")}</div></div></div>')
        body.append(f'<div style="margin-top:var(--space-4)">{_table_block(ch)}</div>')

    # 04 Geographic Overview & Top Landing Pages
    geo, land = g("ga4-by_country_city"), g("ga4-by_landing_page")
    if geo or land:
        body.append(section(4, "Geographic Overview & Top Landing Pages", True))
        if geo:
            body.append(_table_block(geo))
        if land:
            body.append('<h4 style="margin-top:var(--space-6)">Top landing pages</h4>' + _table_block(land))

    # 05 Detailed Traffic Summary (device/browser/os/language)
    quad = [("By device", g("ga4-by_device")), ("By browser", g("ga4-by_browser")),
            ("By operating system", g("ga4-by_operating_system")), ("By language", g("ga4-by_language"))]
    if any(b for _, b in quad):
        body.append(section(5, "Detailed Traffic Summary", True))
        cells = "".join(f'<div><h5>{esc(t)}</h5>{_table_block(b)}</div>' for t, b in quad if b)
        body.append(f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-6)">{cells}</div>')

    # 06 Search Console
    gsc_grid, gsc_trend = g("gsc-overview"), g("gsc-trend")
    if gsc_grid or gsc_trend:
        body.append(section(6, "Search Console Performance", True))
        if _rich(g("gsc-notes")):
            body.append(f'<div style="max-width:38em">{_rich(g("gsc-notes"))}</div>')
        gc = _metric_cards(gsc_grid, prev_label)
        if gc:
            body.append(f'<div style="margin-top:var(--space-4)"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--space-3)">{gc}</div></div>')
        if gsc_trend and _chart_points(gsc_trend):
            body.append('<h4 style="margin-top:var(--space-8)">Clicks &amp; impressions trend</h4>'
                        + report_pdf._chart_page(gsc_trend).split("</h2>")[-1] if False else "")
            # keep it simple + on-brand: reuse the app's line renderer body inside a blueprint card
            body.append('<div class="card blueprint" style="padding:var(--space-4)"><i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>'
                        + _line_svg(_chart_points(gsc_trend)) + '</div>')

    # 07 Keyword Rankings
    kw = g("keywords")
    if kw:
        body.append(section(7, "Keyword Rankings", True) + _table_block(kw))

    # 08 New Backlinks — summary
    bl = g("backlinks")
    bl_items = [it for it in (bl or {}).get("items", []) if _included(it)]
    if bl:
        cnt = bl.get("count", len(bl_items))
        body.append(section(8, "New Backlinks", True)
                    + f'<p style="max-width:38em">This month added <strong>{esc(cnt)}</strong> new backlinks.</p>')

    # 09 Backlink Placements — the actual backlink URLs + any blog/LinkedIn posts
    blogs = [i for i in (g("posts-blogs") or {}).get("items", []) if _included(i)]
    li = [i for i in (g("posts-linkedin") or {}).get("items", []) if _included(i)]
    prows = ([[it.get("url"), "New backlink"] for it in bl_items]
             + [[i.get("url"), "Blog post"] for i in blogs]
             + [[i.get("url"), "LinkedIn post"] for i in li])
    if prows:
        body.append(section(9, "Backlink Placements", True) + table(["Source", "Type"], prows))

    # 10 Targets & Goals
    tg = g("targets")
    if tg:
        body.append(section(10, "Targets & Goals", True) + _targets_table(tg))

    # 11 Strategy & Notes
    st = g("strategy")
    if st and _rich(st):
        body.append(section(11, "Strategy & Notes")
                    + f'<div style="max-width:42em">{_rich(st)}</div>')

    # ── assemble the document (no web component: direct flow + @page boxes) ──
    css = _asset("ds-industry.css")
    cover = ('<div style="display:flex;flex-direction:column;justify-content:flex-start;min-height:8.6in;break-after:page">'
             '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:64px">'
             '<div style="width:190px;height:68px;border:1px solid var(--color-divider);display:flex;align-items:center;justify-content:center;font-family:var(--font-heading);font-size:11px;letter-spacing:.12em;color:#b7b7ba">CLIENT LOGO</div>'
             '<div style="width:190px;height:68px;border:1px solid var(--color-divider);display:flex;align-items:center;justify-content:center;font-family:var(--font-heading);font-size:11px;letter-spacing:.12em;color:#b7b7ba">AGENCY LOGO</div></div>'
             f'<h6 style="color:var(--color-accent)">Monthly SEO Report — {esc(period_label)}</h6>'
             f'<h1 style="font-size:58px;margin:10px 0 0;max-width:11em">{esc(project)}</h1></div>')
    thankyou = ('<div style="break-before:page;display:flex;flex-direction:column;justify-content:flex-start;padding-top:96px;min-height:8.6in">'
                '<h6 style="color:var(--color-accent)">Thank You</h6>'
                '<h1 style="font-size:44px;margin:10px 0 var(--space-4);max-width:10em">Thank you for reading.</h1>'
                '<p style="font-size:17px;max-width:32em">If you have any questions or would like to discuss our findings further, please reach out.</p></div>')
    hdr_title = _js_str(f"{project} · MONTHLY SEO REPORT")
    ft_left = _js_str(f"Reporting period: {period_range} · Prepared by InfyApp for {project}")
    print_css = (
        "@page{size:A4;margin:22mm 14mm 16mm;"
        f'@top-center{{content:"{hdr_title}";font-family:\'Barlow Condensed\',sans-serif;font-size:9pt;letter-spacing:.14em;color:#5980a6;}}'
        f'@bottom-left{{content:"{ft_left}";font-family:Barlow,sans-serif;font-size:7.5pt;color:#8a8a8d;}}'
        '@bottom-right{content:counter(page) " / " counter(pages);font-family:Barlow,sans-serif;font-size:9pt;color:#7a7a7d;}'
        "}"
        "html,body{background:#fff;margin:0;}"
        "@media print{.card,svg,table,h4,h5,.blueprint{break-inside:avoid}}"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<title>{esc(project)} — Monthly SEO Report</title>'
        '<style>@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}</style>'
        f'<style>{css}</style><style>{print_css}</style></head><body>'
        + cover + "".join(body) + thankyou +
        '</body></html>'
    )


def _js_str(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


def _line_svg(points):
    """Two-axis clicks/impressions line in the template's style (680×272)."""
    n = len(points) or 1
    x0, xr, yt, yb = 40, 634, 16, 228
    pw, ph = xr - x0, yb - yt
    clicks = [_num(p.get("clicks")) or 0 for p in points]
    imps = [_num(p.get("impressions")) or 0 for p in points]
    cmax = max(clicks) or 1
    imax = max(imps) or 1
    def x(i): return x0 + (pw * i / (n - 1) if n > 1 else pw / 2)
    def yc(v): return yb - ph * (v / cmax)
    def yi(v): return yb - ph * (v / imax)
    grid = (f'<line x1="{x0}" y1="{yb}" x2="{xr}" y2="{yb}" stroke="#7a7a7d" stroke-width="1"/>'
            f'<line x1="{x0}" y1="{yt}" x2="{x0}" y2="{yb}" stroke="#416180" stroke-width="1"/>'
            f'<line x1="{xr}" y1="{yt}" x2="{xr}" y2="{yb}" stroke="#98989b" stroke-width="1"/>')
    dimp = "M " + " L ".join(f"{x(i):.1f},{yi(v):.1f}" for i, v in enumerate(imps))
    dclk = "M " + " L ".join(f"{x(i):.1f},{yc(v):.1f}" for i, v in enumerate(clicks))
    paths = (f'<path d="{dimp}" fill="none" stroke="#98989b" stroke-width="2" stroke-dasharray="5 3"/>'
             f'<path d="{dclk}" fill="none" stroke="#416180" stroke-width="2.2"/>')
    return (f'<svg viewBox="0 0 680 272" width="100%" style="max-width:680px;display:block" role="img" aria-label="Clicks and impressions trend">'
            + grid + paths + '</svg>')


def _targets_table(block):
    cols = block.get("columns") or []
    fields = block.get("fields") or []
    values = block.get("values") or {}
    if not fields:
        return ""
    headers = ["Metric"] + [c.get("label") for c in cols]
    rows = []
    for f in fields:
        row = [f.get("label")]
        for c in cols:
            row.append((values.get(c.get("key")) or {}).get(f.get("key")) or "—")
        rows.append(row)
    return table(headers, rows)
