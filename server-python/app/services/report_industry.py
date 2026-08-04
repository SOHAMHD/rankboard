import os
import re
from html import escape as _e

from ..config import AGENCY_NAME

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


_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|rgba?\([0-9,.\s%]+\)|[a-zA-Z]{1,32})$")


def _safe_color(v):
    s = ("" if v is None else str(v)).strip()
    return s if _COLOR_RE.match(s) else None


_DATA_IMAGE_RE = re.compile(r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=\s]+$", re.I)


def _safe_image_src(v) -> str:
    s = "" if v is None else str(v)
    return esc(s) if _DATA_IMAGE_RE.match(s) else ""


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def bar_chart(points, active_key="activeUsers", new_key="newUsers", month_label="") -> str:
    n = len(points) or 1
    W, H = 680, 272
    x0, xr, yt, yb = 40, 666, 16, 228
    plot_w, plot_h = xr - x0, yb - yt
    vals = [v for p in points for v in (_num(p.get(active_key)), _num(p.get(new_key))) if v is not None]
    vmax = max(vals) if vals else 1
    import math
    top = max(5, int(math.ceil(vmax / 5.0) * 5))
    def y(v): return yb - plot_h * (v / top)
    parts = []
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
    parts.append(f'<text transform="rotate(-90 13 122)" x="13" y="122" text-anchor="middle" font-size="10" fill="#5d5d60" font-family="Barlow, sans-serif">Users (Y-axis)</text>')
    xaxis = f"Date — {month_label}" if month_label else "Date"
    parts.append(f'<text x="353" y="268" text-anchor="middle" font-size="10" fill="#5d5d60" font-family="Barlow, sans-serif">{esc(xaxis)} (X-axis)</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" style="max-width:680px;display:block" role="img" aria-label="Daily users">'
            + "".join(parts) + "</svg>")


_PIE_COLORS = ["#3366a6", "#d97a34", "#3f9b6a", "#b0498a",
               "#7a5ba6", "#c9a227", "#2f8f9e", "#c0504d",
               "#5a6b7a", "#8f5b3c"]


def donut(slices, total_label="", center_value=None) -> str:
    palette = _PIE_COLORS
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
    shown = total if center_value is None else max(0, _num(center_value) or 0)
    center = esc(int(shown)) if total_label else ""
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


def _posts_table(items) -> str:
    trs = []
    for it in items or []:
        url = (it or {}).get("url") or ""
        title = (it or {}).get("title") or "—"
        link = (f'<a href="{esc(url)}" style="color:#424242;text-decoration:underline;word-break:break-all">{esc(url)}</a>'
                if url else "—")
        trs.append(f"<tr><td>{esc(title)}</td><td>{link}</td></tr>")
    return ('<table class="table table-left"><thead><tr><th>Title</th><th>Link</th></tr></thead>'
            f'<tbody>{"".join(trs)}</tbody></table>')


def _keyword_table_html(block):
    from . import report_pdf
    cols = [c for c in (block.get("columns") or []) if c.get("kind") != "delta"]
    th = '<th>Sr No.</th>' + "".join(f"<th>{esc(c.get('label'))}</th>" for c in cols)
    trs = []
    i = 0
    for r in block.get("rows") or []:
        if not _included(r):
            continue
        i += 1
        cells = r.get("cells") or {}
        # Shared with the other report designs so a keyword is shaded the same way
        # everywhere. Notably this treats "wasn't ranking -> ranking" as improved
        # and "was ranking -> gone" as declined; the old local comparison required
        # both ranks to be numbers and so left both cases unshaded.
        tone = report_pdf._rank_tone(cells.get("previous_rank"), cells.get("current_rank"))
        style = (' style="background:rgba(22,163,74,0.16)"' if tone == "row-up"
                 else ' style="background:rgba(220,38,38,0.14)"' if tone == "row-down" else "")
        tds = [f'<td>{i}</td>']
        for c in cols:
            v = cells.get(c.get("key"))
            if c.get("kind") == "dim":
                tds.append(f"<td>{esc(v)}</td>")
            else:
                tds.append(f"<td>{esc(_fmt(c.get('type'), v))}</td>")
        trs.append(f"<tr{style}>{''.join(tds)}</tr>")
    return f'<table class="table table-kwleft"><thead><tr>{th}</tr></thead><tbody>{"".join(trs)}</tbody></table>'


def section(n: int, title: str, break_before: bool = False) -> str:
    after_prev = '<div style="height:10px"></div>'
    lead = ('<div style="break-before:page;height:10px"></div>' if break_before
            else '<div style="height:56px"></div>')
    return (after_prev + lead
            + f'<h6 style="color:var(--color-accent);margin-bottom:8px">Section {n:02d}</h6>'
            + f'<h2 style="margin-bottom:var(--space-4)">{esc(title)}</h2>')


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
                elif mt == "underline":
                    txt = f"<u>{txt}</u>"
                elif mt in ("textStyle", "color", "highlight"):
                    col = _safe_color((m.get("attrs") or {}).get("color"))
                    if col:
                        txt = f'<span style="color:{col}">{txt}</span>'
            out.append(txt)
        elif t == "hardBreak":
            out.append("<br>")
        elif nd.get("content"):
            out.append(_inline(nd.get("content")))
    return "".join(out)


def _block_node(nd):
    t = nd.get("type")
    if t == "paragraph":
        inner = _inline(nd.get("content"))
        return f"<p>{inner}</p>" if inner.strip() else '<p class="blank"></p>'
    if t == "heading":
        lvl = (nd.get("attrs") or {}).get("level") or 4
        try:
            lvl = min(max(int(lvl), 1), 6)
        except Exception:
            lvl = 4
        return f"<h{lvl}>{_inline(nd.get('content'))}</h{lvl}>"
    if t in ("bulletList", "orderedList"):
        tag = "ol" if t == "orderedList" else "ul"
        lis = []
        for li in nd.get("content") or []:
            parts = "".join(_block_node(k) for k in li.get("content") or [])
            if parts.replace('<p class="blank"></p>', "").strip() == "":
                lis.append('<li class="blank"></li>')
            else:
                lis.append(f"<li>{parts}</li>")
        return f"<{tag}>{''.join(lis)}</{tag}>"
    if t == "blockquote":
        return "<blockquote>" + "".join(_block_node(k) for k in nd.get("content") or []) + "</blockquote>"
    if t == "codeBlock":
        return f"<pre>{_inline(nd.get('content'))}</pre>"
    if t == "horizontalRule":
        return "<hr>"
    if t == "hardBreak":
        return "<br>"
    if nd.get("content"):
        return "".join(_block_node(k) for k in nd.get("content"))
    return ""


def _doc_html(doc):
    if not isinstance(doc, dict):
        return ""
    return "".join(_block_node(nd) for nd in doc.get("content") or [])


def _rich(block):
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
                    if not title and ":" in rest:
                        lead, tail = rest.split(":", 1)
                        if len(lead.split()) <= 6:
                            title, rest = lead.strip(), tail.strip()
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
        out = report_pdf._fmt_value(type_, val)
    except Exception:
        out = "" if val is None else str(val)
    return out.replace("#", "") if isinstance(out, str) else out


def _metric_cards(block, prev_label="Prev"):
    if not block:
        return ""
    out = []
    for m in block.get("metrics") or []:
        if m.get("currentValue") is None:
            # Don't print an empty tile. A metric with no value (e.g. Domain
            # Authority when Moz is not configured) previously rendered as a
            # lone em-dash sitting next to prose that quoted a real figure.
            continue
        cur = _fmt(m.get("type"), m.get("currentValue"))
        prev = m.get("previousValue")
        meta = f"{prev_label}: {_fmt(m.get('type'), prev)}" if prev is not None else ""
        out.append(card(kicker=m.get("label"), title=cur, meta=meta))
    return "".join(out)


def _with_manual_fallbacks(metrics_block, targets_block):
    """Backfill Key Metrics values the automated sources couldn't supply.

    Domain Authority comes from Moz, but the operator also types it into the
    Targets & Goals grid. When Moz is unavailable the tile went blank while the
    Targets table showed the real number two pages later. Prefer the API value
    and fall back to the figure the operator entered.
    """
    if not metrics_block:
        return metrics_block
    manual = ((targets_block or {}).get("values") or {}).get("previous") or {}
    if not manual:
        return metrics_block
    metrics = []
    changed = False
    for m in metrics_block.get("metrics") or []:
        if m.get("currentValue") is None:
            fallback = manual.get(m.get("key"))
            if fallback not in (None, ""):
                m = {**m, "currentValue": _num(fallback) if _num(fallback) is not None else fallback}
                changed = True
        metrics.append(m)
    if not changed:
        return metrics_block
    return {**metrics_block, "metrics": metrics}


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


def _agency_logo():
    from . import report_pdf
    try:
        return report_pdf._logo_uri()
    except Exception:
        return ""


def _wave_band():
    from . import report_pdf
    try:
        uri = report_pdf._wave_uri()
    except Exception:
        uri = None
    if not uri:
        return _topo_svg()
    return (f'<img src="{uri}" alt="" style="position:absolute;top:10mm;right:0;'
            f'height:calc(100% - 20mm);width:100mm;object-fit:contain;object-position:right center;z-index:0">')


def _topo_svg():
    paths = []
    for i in range(16):
        k = i * 7
        d = (f"M {300+k} {40} C {520+k} {120+k}, {560+k} {360+k}, {360+k} {520+k} "
             f"S {180+k} {860+k}, {430+k} {1020+k} S {620+k} {1300}, {380+k} {1460}")
        paths.append(f'<path d="{d}" fill="none" stroke="#c4c4c4" stroke-width="1" opacity="0.55"/>')
    return (f'<svg viewBox="0 0 760 1500" preserveAspectRatio="xMidYMid slice" '
            f'style="position:absolute;top:0;right:-40px;width:60%;height:100%;z-index:0">{"".join(paths)}</svg>')


def _icon(name):
    c = 'stroke="#424242" stroke-width="1.6" fill="none" stroke-linecap="round" stroke-linejoin="round"'
    paths = {
        "building": '<rect x="4" y="3" width="10" height="18" rx="1"/><path d="M17 8h3v13h-3"/><path d="M7 7h2M7 11h2M7 15h2"/>',
        "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
        "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 9h18M8 3v4M16 3v4"/>',
        "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 4-6 8-6s8 2 8 6"/>',
    }
    return f'<svg viewBox="0 0 24 24" width="22" height="22" {c}>{paths.get(name,"")}</svg>'


def _info_row(icon, label, value_html):
    return (f'<div style="display:flex;align-items:center;gap:16px;padding:14px 0">'
            f'<div style="width:52px;height:52px;flex:none;border-radius:50%;background:#ededed;display:flex;align-items:center;justify-content:center">{_icon(icon)}</div>'
            f'<div><div style="font-size:11px;letter-spacing:.12em;color:#8a8a8d;text-transform:uppercase;font-family:Barlow,sans-serif">{esc(label)}</div>'
            f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-weight:600;font-size:20px;color:#2b2b2b;margin-top:2px">{value_html}</div></div></div>')


def _cover(project, domain, period_label, period_range, client_logo, agency_logo):
    NAVY, BLUE = "#0a2540", "#5980a6"
    client_img = (f'<img src="{esc(client_logo)}" style="max-height:56px;max-width:230px;object-fit:contain">'
                  if client_logo else f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-weight:600;font-size:20px;color:{NAVY}">{esc(project)}</div>')
    agency_img = f'<img src="{esc(agency_logo)}" style="max-height:56px;max-width:230px;object-fit:contain">' if agency_logo else ""
    dom = f'<span style="display:inline-flex;align-items:center;gap:6px;font-family:Barlow,sans-serif;font-weight:400;font-size:14px;color:{BLUE}">{_icon("globe")}{esc(domain)}</span>' if domain else ""
    dom_block = f'<div style="margin-top:3px">{dom}</div>' if dom else ""
    prepared_for = f'<div>{esc(project)}</div>{dom_block}'
    return f'''<div style="position:relative;min-height:100vh;box-sizing:border-box;overflow:hidden;break-after:page">
      {_wave_band()}
      <div style="position:relative;z-index:1;padding:20mm 16mm;max-width:150mm">
        <div style="display:flex;align-items:center;gap:22px;margin-bottom:64px">
          {client_img}<span style="width:1px;height:52px;background:#d4d4d7"></span>{agency_img}
        </div>
        <h1 style="font-family:\'Barlow Condensed\',sans-serif;font-weight:600;line-height:.92;margin:0;letter-spacing:-.01em">
          <span style="display:block;font-size:82px;color:{NAVY}">MONTHLY</span>
          <span style="display:block;font-size:82px;color:{BLUE}">SEO</span>
          <span style="display:block;font-size:82px;color:{NAVY}">REPORT</span>
        </h1>
        <div style="width:120px;height:4px;background:{BLUE};margin:26px 0 20px"></div>
        <div style="font-family:\'Barlow Condensed\',sans-serif;font-weight:600;font-size:40px;color:{BLUE}">{esc(period_label)}</div>
        <div style="margin-top:56px;max-width:520px">
          {_info_row("building","Prepared for", prepared_for)}
          <div style="height:1px;background:#e4e4e6"></div>
          {_info_row("calendar","Reporting period", esc(period_range))}
          <div style="height:1px;background:#e4e4e6"></div>
          {_info_row("user","Prepared by", AGENCY_NAME)}
        </div>
      </div>
    </div>'''


def header_html(project, client_logo, agency_logo):
    ci = f'<img src="{esc(client_logo)}" style="height:40px;max-width:200px;object-fit:contain">' if client_logo else f'<span style="font-family:sans-serif;font-size:9px;color:#8a8a8d">{esc(project)}</span>'
    ai = f'<img src="{esc(agency_logo)}" style="height:40px;max-width:200px;object-fit:contain">' if agency_logo else ""
    return (f'<div style="width:100%;box-sizing:border-box;padding:6px 14mm 4px;display:flex;align-items:center;'
            f'justify-content:space-between;border-bottom:1px solid #e4e4e6;-webkit-print-color-adjust:exact;print-color-adjust:exact">'
            f'{ci}<span style="flex:1"></span>{ai}</div>')


def footer_html(project):
    return ('<div style="width:100%;box-sizing:border-box;padding:2px 14mm 6px;display:flex;align-items:center;'
            'font-family:sans-serif;font-size:8px;color:#7a7a7d">'
            '<span style="flex:1"></span>'
            f'<span style="flex:1;text-align:center">Prepared by {esc(AGENCY_NAME)}</span>'
            '<span style="flex:1;text-align:right"><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')


def render_all(version, blobs=None):
    content = version.get("content") or {}
    header = next((b for b in (content.get("blocks") or []) if b.get("type") == "report_header"), {})
    project = header.get("projectName") or (content.get("project") or {}).get("name") or "SEO Report"
    client_logo = _safe_image_src(header.get("clientLogo"))
    agency = _agency_logo()
    return {"html": render_document(version, blobs),
            "cover": render_document(version, blobs, part="cover"),
            "body": render_document(version, blobs, part="body"),
            "header": header_html(project, client_logo, agency),
            "footer": footer_html(project)}


_SECTION_OF = {
    "progress-summary": 1, "key-metrics": 1, "achievements": 1,
    "ga4-overview-notes": 2, "ga4-overview": 2, "ga4-users-trend": 2, "ga4-graph-notes": 2,
    "ga4-channel-notes": 3, "ga4-by_channel": 3,
    "ga4-cities-notes": 4, "ga4-by_country_city": 4, "ga4-landing-notes": 4, "ga4-by_landing_page": 4,
    "ga4-by_device": 5, "ga4-by_browser": 5, "ga4-by_operating_system": 5, "ga4-by_language": 5,
    "gsc-notes": 6, "gsc-overview": 6, "gsc-trend": 6,
    "keywords": 7, "backlinks": 8, "posts-blogs": 9, "posts-linkedin": 9,
    "targets": 10, "targets-notes": 10, "strategy": 11,
}


def render_document(version, blobs=None, part="all") -> str:
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

    body = [section(1, "Progress Summary")]

    extras = {}
    cur_sec = 1
    for b in content.get("blocks") or []:
        bidd = b.get("id")
        if bidd in _SECTION_OF:
            cur_sec = _SECTION_OF[bidd]
        elif b.get("type") == "narrative" and bidd not in _SECTION_OF:
            h = _rich(b)
            if h.strip():
                extras.setdefault(cur_sec, []).append(h)

    _ex_used = set()

    def ex(n):
        _ex_used.add(n)
        return "".join(f'<div style="max-width:40em;margin-top:var(--space-3)">{h}</div>'
                       for h in extras.get(n, []))
    if maturing:
        body.append(f'<p class="text-muted" style="font-style:italic;font-size:12.5px;max-width:38em">{esc(maturing)}</p>')
    if _rich(g("progress-summary")):
        body.append(f'<div style="font-size:16px;max-width:38em;margin-top:var(--space-3)">{_rich(g("progress-summary"))}</div>')
    cards = _metric_cards(_with_manual_fallbacks(g("key-metrics"), g("targets")), prev_label)
    if cards:
        body.append(f'<div style="margin-top:var(--space-6)"><div style="display:grid;grid-template-columns:repeat(3,1fr);gap:var(--space-3)">{cards}</div></div>')
    pairs = _list_items(g("achievements"))
    if pairs:
        body.append('<h4 style="margin-top:var(--space-8)">Key achievements</h4>')
        cc = "".join(card(title=("" if t == "Highlight" else t), body=b, title_size=16)
                     for t, b in pairs[:8])
        body.append(f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-3);margin-top:var(--space-3)">{cc}</div>')
    body.append(ex(1))

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
    if _rich(g("ga4-graph-notes")):
        body.append(f'<div class="text-muted" style="font-size:12.5px;margin-top:var(--space-3);max-width:40em">{_rich(g("ga4-graph-notes"))}</div>')
    body.append(ex(2))

    ch = g("ga4-by_channel")
    if ch:
        body.append(section(3, "Traffic by Channel", True))
        if ex(3):
            body.append(ex(3))
        cols = ch.get("columns") or []
        tu_key = next((c.get("key") for c in cols if c.get("key") == "totalUsers"), None) \
                 or next((c.get("key") for c in cols if c.get("kind") == "metric"), None)
        rows = [r for r in (ch.get("rows") or []) if _included(r)]
        slices = []
        for r in rows:
            cells = r.get("cells") or {}
            slices.append({"label": cells.get("dim0"), "value": _num(cells.get(tu_key)) or 0})
        total = sum(s["value"] for s in slices) or 1
        _ov = g("ga4-overview") or {}
        _center = next(
            (m.get("currentValue") for m in (_ov.get("metrics") or [])
             if m.get("key") == "totalUsers" and m.get("currentValue") is not None),
            None,
        )
        legend = "".join(
            f'<div style="display:flex;align-items:center;gap:8px;font-size:13px"><i style="width:10px;height:10px;flex:none;background:{c}"></i>'
            f'<span style="flex:1">{esc(s["label"])}</span><span class="text-muted">{round(s["value"]/total*100)}%</span></div>'
            for s, c in zip(slices, _PIE_COLORS * 3))
        channel_notes = _rich(g("ga4-channel-notes"))
        body.append(
            (f'<div style="max-width:44em;margin-bottom:var(--space-4)">{channel_notes}</div>'
             if channel_notes.strip() else "")
            + '<div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-8);align-items:center">'
            + f'<div style="display:flex;flex-direction:column;gap:9px">{legend}</div>'
            + '<div class="card blueprint"><i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>'
            + '<div class="card-kicker">Share of total users</div>'
            + f'<div style="display:flex;justify-content:center;padding:var(--space-2) 0">{donut(slices, "total users", center_value=_center)}</div></div>'
            + '</div>')
        body.append(f'<div style="margin-top:var(--space-4)">{_table_block(ch)}</div>')
        if _center is not None and total > (_num(_center) or 0):
            body.append(
                '<div class="text-muted" style="font-size:11.5px;margin-top:var(--space-2);max-width:46em">'
                'Note: channel rows add up to more than the period total because a visitor who '
                'arrives through more than one channel is counted in each channel, but only once '
                'in the overall total.</div>'
            )

    geo, land = g("ga4-by_country_city"), g("ga4-by_landing_page")
    if geo or land:
        body.append(section(4, "Geographic Overview & Top Landing Pages", True))
        if _rich(g("ga4-cities-notes")):
            body.append(f'<div style="max-width:38em">{_rich(g("ga4-cities-notes"))}</div>')
        if geo:
            body.append(_table_block(geo))
            body.append(
                '<p class="text-muted" style="font-size:11.5px;line-height:1.5;margin-top:var(--space-3);max-width:48em">'
                '(<strong>Note:</strong> Engaged sessions are visits that lasted 10+ seconds, triggered a key '
                'event, or included 2 or more page views; Engagement rate is the share of sessions that were '
                'engaged; Avg. engagement is the average engagement time per active user.)</p>')
        if land or _rich(g("ga4-landing-notes")):
            # No hard page break here. A forced break used to leave the geographic
            # table's footnote stranded alone on its own page whenever the table ran
            # long enough to push the note past the page boundary. Keeping the whole
            # landing-pages block together with break-inside:avoid lets it move to the
            # next page only when it genuinely doesn't fit, which also saves a page.
            landing = ['<h4 style="margin-top:var(--space-6)">Top landing pages</h4>']
            if _rich(g("ga4-landing-notes")):
                landing.append(f'<div style="max-width:38em;margin-bottom:var(--space-3)">{_rich(g("ga4-landing-notes"))}</div>')
            if land:
                landing.append(_table_block(land).replace('class="table"', 'class="table table-left"', 1))
                landing.append(
                    '<p class="text-muted" style="font-size:11.5px;line-height:1.5;margin-top:var(--space-3);max-width:48em">'
                    '(<strong>Note:</strong> “/” is the website home page; other rows show the page path — '
                    'e.g. /contact-us/ is the Contact Us page.)</p>')
            body.append('<div style="break-inside:avoid">' + "".join(landing) + '</div>')
        body.append(ex(4))

    quad = [("By device", g("ga4-by_device")), ("By language", g("ga4-by_language")),
            ("By operating system", g("ga4-by_operating_system")), ("By browser", g("ga4-by_browser"))]
    if any(b for _, b in quad):
        body.append(section(5, "Detailed Traffic Summary", True))
        cells = "".join(f'<div><h5>{esc(t)}</h5>{_table_block(b)}</div>' for t, b in quad if b)
        body.append(f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-6)">{cells}</div>')
        body.append(ex(5))

    gsc_grid, gsc_trend = g("gsc-overview"), g("gsc-trend")
    if gsc_grid or gsc_trend:
        body.append(section(6, "Search Console Performance", True))
        if _rich(g("gsc-notes")):
            body.append(f'<div style="max-width:38em">{_rich(g("gsc-notes"))}</div>')
        gc = _metric_cards(gsc_grid, prev_label)
        if gc:
            body.append(f'<div style="margin:var(--space-6) 0 var(--space-8)"><div style="display:grid;grid-template-columns:repeat(4,1fr);gap:var(--space-4)">{gc}</div></div>')
        if gsc_trend and _chart_points(gsc_trend):
            body.append('<h4 style="margin-top:var(--space-6);margin-bottom:var(--space-3)">Performance trend</h4>')
            body.append(_gsc_chart(gsc_trend))
            body.append(
                '<p class="text-muted" style="font-size:11.5px;line-height:1.5;margin-top:var(--space-3);max-width:48em">'
                '(<strong>Note:</strong> Each chart tracks one Search Console dimension over the period — '
                '<strong>Clicks</strong> is the number of times users clicked through to the site from Google search; '
                '<strong>Impressions</strong> is how many times the site appeared in search results; '
                '<strong>CTR</strong> (click-through rate) is Clicks divided by Impressions, i.e. the share of '
                'appearances that earned a click; and <strong>Avg. position</strong> is the site’s average ranking '
                'in search results, where a lower number is better — position 1 being the top result.)</p>')
        body.append(ex(6))

    kw = g("keywords")
    if kw:
        body.append(section(7, "Keyword Rankings", True) + _keyword_table_html(kw))
        body.append(ex(7))

    bl = g("backlinks")
    bl_items = [it for it in (bl or {}).get("items", []) if _included(it)]
    if bl:
        cnt = bl.get("count", len(bl_items))
        body.append(section(8, "New Backlinks", True)
                    + f'<p style="max-width:38em">This month, we acquired <strong>{esc(cnt)}</strong> backlinks.</p>')
        if bl_items:
            body.append('<h4 style="margin-top:var(--space-6)">Backlink placements</h4>')
            rows = [[i + 1, it.get("url")] for i, it in enumerate(bl_items)]
            body.append(table(["Sr No.", "Backlinks list"], rows)
                        .replace('class="table"', 'class="table table-left table-bl"', 1))
        body.append(ex(8))

    blogs = [i for i in (g("posts-blogs") or {}).get("items", []) if _included(i)]
    li = [i for i in (g("posts-linkedin") or {}).get("items", []) if _included(i)]
    if blogs or li:
        body.append(section(9, "Blogs and Posts", True))
        if blogs:
            body.append('<h4 style="margin-top:var(--space-6)">Blog Posts</h4>' + _posts_table(blogs))
        if li:
            body.append('<h4 style="margin-top:var(--space-6)">LinkedIn Posts</h4>' + _posts_table(li))
        body.append(ex(9))

    tg = g("targets")
    if tg:
        notes_html = _rich(g("targets-notes"))
        body.append(section(10, "Targets & Goals", True) + _targets_table(tg)
                    + (f'<h4 style="margin-top:var(--space-6)">Focus areas</h4><div style="max-width:42em">{notes_html}</div>' if notes_html else ""))
        body.append(ex(10))

    st = g("strategy")
    if st and _rich(st):
        body.append(section(11, "Strategy & Notes", True)
                    + f'<div style="max-width:42em">{_rich(st)}</div>')
        body.append(ex(11))

    leftover = "".join(
        "".join(f'<div style="max-width:40em;margin-top:var(--space-3)">{h}</div>'
                for h in extras.get(n, []))
        for n in sorted(extras) if n not in _ex_used
    )
    if leftover:
        body.append('<div style="height:24px"></div>' + leftover)

    css = _asset("ds-industry.css")
    cover = _cover(project, domain, period_label, period_range, _safe_image_src(header.get("clientLogo")), _agency_logo())
    ty_navy, ty_blue = "#0a2540", "#2f5fd0"
    ty_client_logo = _safe_image_src(header.get("clientLogo"))
    ty_client = (
        f'<img src="{esc(ty_client_logo)}" style="max-height:52px;max-width:230px;object-fit:contain">'
        if ty_client_logo
        else f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-weight:600;font-size:20px;color:{ty_navy}">{esc(project)}</div>'
    )
    ty_agency_uri = _agency_logo()
    ty_agency = (
        f'<img src="{esc(ty_agency_uri)}" style="max-height:52px;max-width:230px;object-fit:contain">'
        if ty_agency_uri else ""
    )
    ty_chat_icon = (
        '<svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="#2f5fd0" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M21 11.5a8.4 8.4 0 0 1-8.5 8.5 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8A8.5 8.5 0 0 1 21 11.5z"/>'
        '<circle cx="8.5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="15.5" cy="12" r="1"/></svg>'
    )
    def _ci_svg(body: str) -> str:
        return (
            f'<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="{ty_blue}" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" '
            f'style="flex:none;display:block">{body}</svg>'
        )

    ic_phone = _ci_svg(
        '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2'
        'A2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.3 1.8.6 2.6a2 2 0 0 1-.5 2.1L8.1 9.6a16 16 0 0 0 6 6l1.2-1.2'
        'a2 2 0 0 1 2.1-.5c.8.3 1.7.5 2.6.6a2 2 0 0 1 1.7 2z"/>'
    )
    ic_mail = _ci_svg(
        '<rect x="2" y="4" width="20" height="16" rx="2"/><path d="m2.5 6.5 9.5 7 9.5-7"/>'
    )
    ic_globe = _ci_svg(
        '<circle cx="12" cy="12" r="9.5"/><path d="M2.5 12h19"/>'
        '<path d="M12 2.5a15 15 0 0 1 0 19 15 15 0 0 1 0-19z"/>'
    )
    ic_pin = _ci_svg(
        '<path d="M20 10.5c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0z"/><circle cx="12" cy="10.5" r="2.8"/>'
    )
    thankyou = (
        '<div style="position:relative;min-height:100vh;box-sizing:border-box;overflow:hidden;break-before:page">'
        f'{_wave_band()}'
        '<div style="position:relative;z-index:1;padding:24mm 16mm;max-width:150mm">'
        '<div style="display:flex;align-items:center;gap:22px;margin-bottom:64px">'
        f'{ty_client}<span style="width:1px;height:48px;background:#d4d4d7"></span>{ty_agency}</div>'
        f'<h1 style="font-family:\'Barlow Condensed\',sans-serif;font-weight:700;font-size:70px;'
        f'line-height:.94;margin:0;color:#0067A6">Thank you</h1>'
        '<p style="font-size:17px;max-width:24em;margin-top:var(--space-4);color:#2b2b2b">'
        'If you have any questions or would like to discuss our findings further, please reach out.</p>'
        '<div style="display:flex;align-items:center;gap:18px;margin-top:60px">'
        '<div style="width:62px;height:62px;flex:none;border-radius:50%;background:#eef3fc;'
        f'display:flex;align-items:center;justify-content:center">{ty_chat_icon}</div>'
        f'<div style="border-left:2px solid {ty_blue};padding-left:18px">'
        f'<div style="font-family:\'Barlow Condensed\',sans-serif;font-weight:600;font-size:22px;color:{ty_navy}">'
        'We&rsquo;re here to help.</div>'
        '<div style="font-size:15px;color:#5d5d60;margin-top:2px">Let&rsquo;s keep the growth going.</div>'
        '</div></div>'
        '<div style="margin-top:46px;display:flex;flex-direction:column;gap:12px;'
        'font-size:14px;color:#2b2b2b">'
        f'<div style="display:flex;align-items:center;gap:10px">{ic_phone}'
        f'<span>{esc(report_pdf._AGENCY_PHONE)}</span></div>'
        f'<div style="display:flex;align-items:center;gap:10px">{ic_mail}'
        f'<span>{esc(report_pdf._AGENCY_EMAIL)}</span></div>'
        f'<div style="display:flex;align-items:center;gap:10px">{ic_globe}'
        f'<span><u>{esc(report_pdf._AGENCY_SITE)}</u></span></div>'
        f'<div style="display:flex;align-items:center;gap:10px">{ic_pin}'
        f'<span>{esc(report_pdf._AGENCY_ADDR)}</span></div>'
        '</div>'
        '</div></div>'
    )
    hdr_title = _js_str(f"{project} · MONTHLY SEO REPORT")
    ft_left = _js_str(f"Reporting period: {period_range} · Prepared by {AGENCY_NAME} for {project}")
    heading_css = "h2,h3,h4,h5,h6,.card-title,.card-kicker{color:#0067A6;}"
    breaks = "@media print{.card,svg,h4,h5{break-inside:avoid}tr{break-inside:avoid}}"
    print_css_body = f"@page{{size:A4;margin:24mm 14mm 16mm;}}html,body{{background:#fff;margin:0;}}{heading_css}{breaks}"
    print_css_cover = f"@page{{size:A4;margin:0;}}html,body{{height:100%;background:#fff;margin:0;}}{heading_css}{breaks}"
    print_css_all = ("@page{size:A4;margin:24mm 14mm 16mm;}@page:first{margin:0;}"
                     f"html,body{{background:#fff;margin:0;}}{heading_css}{breaks}")

    head = ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<title>{esc(project)} — Monthly SEO Report</title>'
            '<style>@media print{*{-webkit-print-color-adjust:exact;print-color-adjust:exact}}</style>'
            f'<style>{css}</style>')
    if part == "cover":
        return head + f'<style>{print_css_cover}</style></head><body>' + cover + '</body></html>'
    if part == "body":
        return head + f'<style>{print_css_body}</style></head><body>' + "".join(body) + thankyou + '</body></html>'
    if part == "content":
        print_css_content = f"html,body{{background:#fff;margin:0;}}{heading_css}{breaks}"
        return head + f'<style>{print_css_content}</style></head><body>' + "".join(body) + '</body></html>'
    if part == "thankyou":
        return head + f'<style>{print_css_cover}</style></head><body>' + thankyou + '</body></html>'
    return head + f'<style>{print_css_all}</style></head><body>' + cover + "".join(body) + thankyou + '</body></html>'


def _js_str(s):
    return (s or "").replace("\\", "\\\\").replace('"', '\\"')


_GSC_COLORS = {
    "clicks": "#1f5f8b",
    "impressions": "#5a9bc4",
    "ctr": "#2f8f5b",
    "position": "#c25b45",
}


def _smooth_d(pts):
    if not pts:
        return ""
    if len(pts) < 3:
        return "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in pts)
    n = len(pts)
    d = f"M {pts[0][0]:.1f} {pts[0][1]:.1f}"
    for i in range(n - 1):
        p0 = pts[i - 1] if i > 0 else pts[i]
        p1, p2 = pts[i], pts[i + 1]
        p3 = pts[i + 2] if i + 2 < n else pts[i + 1]
        c1x = p1[0] + (p2[0] - p0[0]) / 6.0
        c1y = p1[1] + (p2[1] - p0[1]) / 6.0
        c2x = p2[0] - (p3[0] - p1[0]) / 6.0
        c2y = p2[1] - (p3[1] - p1[1]) / 6.0
        d += f" C {c1x:.1f} {c1y:.1f} {c2x:.1f} {c2y:.1f} {p2[0]:.1f} {p2[1]:.1f}"
    return d


def _mini_metric_chart(points, key, label, type_):
    vals = [_num(p.get(key)) for p in points]
    nums = [v for v in vals if v is not None]
    n = len(points) or 1
    W, H = 320, 160
    x0, xr, yt, yb = 56, 312, 24, 124
    pw, ph = xr - x0, yb - yt
    color = _GSC_COLORS.get(key, "#416180")

    def xf(k):
        return x0 + (pw * k / (n - 1) if n > 1 else pw / 2)

    def _fx(s):
        s = str(s or "")
        return s[5:] if len(s) >= 10 and s[4:5] == "-" else s

    parts = [f'<text x="{x0}" y="14" font-size="11" font-weight="700" fill="{color}" '
             f'font-family="Barlow,sans-serif">{esc(label)}</text>']
    if not nums:
        parts.append(f'<text x="{W/2:.0f}" y="{H/2:.0f}" text-anchor="middle" font-size="10" fill="#b7b7ba">No data</text>')
    else:
        lo = min(nums) if type_ == "rank" else 0
        hi = max(nums)
        if hi == lo:
            hi = lo + 1
        span = hi - lo
        def yf(v):
            return yb - ph * ((v - lo) / span)
        for gstep in range(0, 3):
            frac = gstep / 2
            gy = yb - ph * frac
            val = lo + span * frac
            parts.append(f'<line x1="{x0}" y1="{gy:.1f}" x2="{xr}" y2="{gy:.1f}" stroke="#e9e9ea" stroke-width="1"/>')
            parts.append(f'<text x="{x0-5}" y="{gy+3:.1f}" text-anchor="end" font-size="8" fill="#98989b">{esc(_fmt(type_, val))}</text>')
        parts.append(f'<line x1="{x0}" y1="{yt}" x2="{x0}" y2="{yb}" stroke="#7a7a7d" stroke-width="1"/>')
        parts.append(f'<line x1="{x0}" y1="{yb}" x2="{xr}" y2="{yb}" stroke="#7a7a7d" stroke-width="1"/>')
        pts = [(xf(k), yf(v)) for k, v in enumerate(vals) if v is not None]
        if pts:
            smooth = _smooth_d(pts)
            area = f'M {pts[0][0]:.1f} {yb:.1f} L ' + smooth[2:] + f' L {pts[-1][0]:.1f} {yb:.1f} Z'
            parts.append(f'<path d="{area}" fill="{color}" fill-opacity="0.13" stroke="none"/>')
            parts.append(f'<path d="{smooth}" fill="none" stroke="{color}" stroke-width="1.6" stroke-linejoin="round"/>')
            for px, py in pts:
                parts.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="1.5" fill="{color}"/>')
        weeks = list(range(0, n, 7))
        if weeks and (n - 1) - weeks[-1] >= 3:
            weeks.append(n - 1)
        for i in weeks:
            cx = xf(i)
            anchor = "start" if i == 0 else ("end" if i == n - 1 else "middle")
            parts.append(f'<line x1="{cx:.1f}" y1="{yb}" x2="{cx:.1f}" y2="{yb+3}" stroke="#7a7a7d" stroke-width="1"/>')
            parts.append(f'<text x="{cx:.1f}" y="{yb+12}" text-anchor="{anchor}" font-size="7.5" fill="#98989b">{esc(_fx(points[i].get("x")))}</text>')
        midy = (yt + yb) / 2
        parts.append(f'<text x="{(x0+xr)/2:.0f}" y="{H-3}" text-anchor="middle" font-size="8" fill="#7a7a7d" font-family="Barlow,sans-serif">Date (X-axis)</text>')
        parts.append(f'<text transform="rotate(-90 10 {midy:.0f})" x="10" y="{midy:.0f}" text-anchor="middle" font-size="8" fill="#7a7a7d" font-family="Barlow,sans-serif">{esc(label)} (Y-axis)</text>')
    return ('<div class="card blueprint" style="padding:8px 10px 6px">'
            '<i class="corner tl"></i><i class="corner tr"></i><i class="corner bl"></i><i class="corner br"></i>'
            f'<svg viewBox="0 0 {W} {H}" width="100%" style="display:block">{"".join(parts)}</svg></div>')


def _gsc_chart(block):
    points = block.get("points") or []
    series = block.get("series") or []
    cards = "".join(_mini_metric_chart(points, s.get("key"), s.get("label"), s.get("type"))
                    for s in series)
    return (f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--space-4)">{cards}</div>')


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
