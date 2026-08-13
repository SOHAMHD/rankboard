import base64
import concurrent.futures
import hashlib
import html
import json
import os
import re
import threading
from collections import OrderedDict
from contextlib import contextmanager

from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent.parent / "assets"


_AGENCY_PHONE = "+91 7304 5050 68"
_AGENCY_EMAIL = "info@infyappdevelopment.com"
_AGENCY_SITE = "infyappdevelopment.com"
_AGENCY_ADDR = "211, Lotus Business Park, Rambaugh Lane,\n Next to Chincholi Signal Petrol Pump,\nMalad West - 400064"


@lru_cache(maxsize=None)
def _data_uri(filename: str, mime: str) -> str:
    raw = (_ASSETS / filename).read_bytes()
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


@lru_cache(maxsize=1)
def _logo_uri() -> str:
    return _data_uri("infapp-logo-trimmed.png", "image/png")


@lru_cache(maxsize=1)
def _wave_uri():
    return _data_uri("wave.png", "image/png") if (_ASSETS / "wave.png").exists() else None


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


def _rank_tone(previous, current):
    """Row tone ("row-up" / "row-down" / "") for a keyword's rank change.

    Deliberately compares the two ranks rather than reading `rank_delta`.
    Breaking into the results from nowhere is the largest possible improvement,
    and falling out of them entirely is the largest possible decline, but both
    leave `rank_delta` as None because one side isn't a number — so a delta-based
    check silently renders the two most significant movements as no change.
    """
    has_prev, has_cur = _num(previous), _num(current)
    if has_prev and has_cur:
        if current < previous:
            return "row-up"
        if current > previous:
            return "row-down"
        return ""
    if has_cur:            # wasn't ranking before, is now
        return "row-up"
    if has_prev:           # was ranking, has dropped out
        return "row-down"
    return ""              # never ranked in either period


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


def _esc(v) -> str:
    return html.escape("" if v is None else str(v))


def _blocks(content: dict) -> list:
    if not content or content.get("type") != "report_document":
        return []
    return content.get("blocks") or []


def _header_block(content: dict) -> dict:
    for b in _blocks(content):
        if b.get("type") == "report_header":
            return b
    return {}


#: All Playwright work runs on this single dedicated thread.
#:
#: Playwright's sync API is bound to the thread that created it, and FastAPI runs
#: sync handlers on an arbitrary threadpool thread — so a browser can't simply be
#: shared as a module global. Funnelling every render through one worker thread
#: means exactly one Chromium process for the whole app, launched once and reused,
#: instead of a fresh ~1-2s cold start per download. It also serialises rendering,
#: which is what we want: three concurrent Chromium instances would thrash.
_pdf_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="pdf-render"
)
_pw_state = threading.local()

#: Ceiling for one render, counted from submission — so it covers queueing behind
#: other renders as well as the render itself. Rendering is serialised on one
#: thread with an unbounded queue, so without a deadline a slow or hung Chromium
#: made every waiting request wait indefinitely.
PDF_RENDER_TIMEOUT = 90
COVER_RENDER_TIMEOUT = 45

#: Refuse work rather than join an unbounded queue. Renders are serialised, so a
#: caller arriving behind this many is going to time out anyway — better to say so
#: immediately than to hold a request open for a minute and a half first.
MAX_RENDER_QUEUE = 8
_render_queue = 0
_render_queue_lock = threading.Lock()


class RenderBusy(RuntimeError):
    """Raised when the render queue is too deep to accept more work."""


class RenderTimeout(RuntimeError):
    """Raised when a render exceeds its deadline."""


@contextmanager
def _queue_slot(limit: int):
    global _render_queue
    with _render_queue_lock:
        if _render_queue >= limit:
            raise RenderBusy(
                "The report renderer is busy. Try again in a moment."
            )
        _render_queue += 1
    try:
        yield
    finally:
        with _render_queue_lock:
            _render_queue -= 1


def _shared_browser():
    """The long-lived Chromium owned by the render thread."""
    browser = getattr(_pw_state, "browser", None)
    if browser is not None:
        try:
            if browser.is_connected():
                return browser
        except Exception:
            pass
    from playwright.sync_api import sync_playwright

    pw = getattr(_pw_state, "pw", None)
    if pw is None:
        pw = sync_playwright().start()
        _pw_state.pw = pw
    _pw_state.browser = pw.chromium.launch()
    return _pw_state.browser


def shutdown_renderer() -> None:
    """Tear down the render thread's browser. Safe to call on shutdown."""
    def _stop():
        browser = getattr(_pw_state, "browser", None)
        if browser is not None:
            try:
                browser.close()
            except Exception:
                pass
            _pw_state.browser = None
        pw = getattr(_pw_state, "pw", None)
        if pw is not None:
            try:
                pw.stop()
            except Exception:
                pass
            _pw_state.pw = None

    try:
        _pdf_executor.submit(_stop).result(timeout=20)
    except Exception:
        pass


#: Re-rendering the same report unchanged is pure waste, so completed renders are
#: kept keyed on the content that actually produced them.
#:
#: Deliberately NOT keyed on frozen_at: report_service.freeze() stamps frozen_at
#: at creation time even for drafts, and save_content() then updates content_json
#: in place without touching it — so frozen_at is not a version marker and using
#: it would serve a stale PDF after any edit. Hashing the content is a few
#: milliseconds against a multi-second render, and is correct by construction.
#: data_json is never mutated after creation, so the version id covers it.
_PDF_CACHE_MAX = int(os.environ.get("REPORT_PDF_CACHE_MAX", "16"))
_pdf_cache: "OrderedDict[tuple, bytes]" = OrderedDict()
_pdf_cache_lock = threading.Lock()


def _pdf_cache_key(version: dict, blobs: list | None):
    vid = version.get("id")
    if vid is None:
        return None
    try:
        payload = json.dumps(
            [version.get("content"), blobs], sort_keys=True, default=str
        ).encode("utf-8")
    except Exception:
        return None
    return (vid, hashlib.sha256(payload).hexdigest())


def render_pdf(version: dict, blobs: list | None = None) -> bytes:
    key = _pdf_cache_key(version, blobs)
    if key is not None:
        with _pdf_cache_lock:
            hit = _pdf_cache.get(key)
            if hit is not None:
                _pdf_cache.move_to_end(key)
                return hit

    with _queue_slot(MAX_RENDER_QUEUE):
        future = _pdf_executor.submit(_render_pdf_on_worker, version, blobs)
        try:
            data = future.result(timeout=PDF_RENDER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            # The worker keeps going — cancelling a Playwright call mid-flight is
            # not safe — but this request stops waiting and gives its slot back.
            raise RenderTimeout(
                f"The report took longer than {PDF_RENDER_TIMEOUT}s to render."
            ) from None

    if key is not None:
        with _pdf_cache_lock:
            _pdf_cache[key] = data
            while len(_pdf_cache) > _PDF_CACHE_MAX:
                _pdf_cache.popitem(last=False)
    return data


def _render_pdf_on_worker(version: dict, blobs: list | None = None) -> bytes:
    """Render the three document parts and stitch them into one PDF.

    There used to be a `except Exception: html_str = render_html(...)` fallback
    here, backed by a second complete renderer in this module. It was removed
    deliberately. The two renderers produced visibly different documents —
    different layout, different page count, no running header or footer — so a
    failure in the primary path silently sent a client a report that looked
    nothing like the last one, with only a print() on stderr to say so. Nothing
    tested the fallback, so it was also free to rot.
    """
    from . import report_industry
    parts = {pt: report_industry.render_document(version, blobs, part=pt)
             for pt in ("cover", "content", "thankyou")}
    # Outside the render above: a missing agency logo is cosmetic and must not be
    # able to fail the document. It previously sat inside the try, so a logo
    # problem alone discarded a perfectly good render.
    try:
        agency = report_industry._agency_logo()
    except Exception as exc:  # noqa: BLE001
        print("report agency logo unavailable:", exc)
        agency = ""

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

    browser = _shared_browser()

    def _to_pdf(html, **kw):
        page = browser.new_page()
        try:
            page.set_content(html, wait_until="networkidle")
            try:
                page.evaluate("() => document.fonts && document.fonts.ready")
            except Exception:
                pass
            page.emulate_media(media="print")
            return page.pdf(**kw)
        finally:
            page.close()

    full_bleed = dict(format="A4", print_background=True, prefer_css_page_size=True,
                      margin={"top": "0", "bottom": "0", "left": "0", "right": "0"})
    # All three pages share the reused browser's HTTP cache, so the webfont CSS
    # and woff2 files are fetched once rather than once per page.
    #
    # Cover and thank-you are full-bleed; only the content pages carry the running
    # header and footer, which is why they can't be one render.
    pdfs = [
        _to_pdf(parts["cover"], **full_bleed),
        _to_pdf(parts["content"], format="A4", print_background=True,
                display_header_footer=True, header_template=header_tpl,
                footer_template=footer_tpl,
                margin={"top": "24mm", "bottom": "14mm", "left": "14mm", "right": "14mm"}),
        _to_pdf(parts["thankyou"], **full_bleed),
    ]

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
    # Runs on the same single render thread, reusing the same Chromium. This used
    # to launch a second browser — so sending a report paid two cold starts.
    with _queue_slot(MAX_RENDER_QUEUE):
        future = _pdf_executor.submit(_render_cover_on_worker, version, blobs, width)
        try:
            return future.result(timeout=COVER_RENDER_TIMEOUT)
        except concurrent.futures.TimeoutError:
            raise RenderTimeout(
                f"The cover image took longer than {COVER_RENDER_TIMEOUT}s to render."
            ) from None


def _render_cover_on_worker(version: dict, blobs: list | None, width: int) -> bytes:
    from . import report_industry

    html = report_industry.render_document(version, blobs, part="cover")

    A4_W, A4_H = 794, 1123
    scale = width / A4_W

    browser = _shared_browser()
    page = browser.new_page(
        viewport={"width": A4_W, "height": A4_H},
        device_scale_factor=scale,
    )
    try:
        page.set_content(html, wait_until="networkidle")
        return page.screenshot(type="png")
    finally:
        page.close()
