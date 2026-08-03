import io

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

COLUMNS = ["keyword"]
MAX_ROWS = 1000


def build_sample_workbook() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Keywords"

    header_fill = PatternFill("solid", start_color="EA580C")
    header_font = Font(bold=True, color="FFFFFF", name="Arial")
    body_font = Font(name="Arial")

    ws.append(["Keyword"])
    cell = ws.cell(row=1, column=1)
    cell.fill = header_fill
    cell.font = header_font
    cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 22

    examples = [
        "online yoga classes",
        "meditation retreat rishikesh",
        "pranayama breathing course",
    ]
    for i, kw in enumerate(examples):
        ws.append([kw])
        ws.cell(row=2 + i, column=1).font = body_font

    ws.column_dimensions["A"].width = 46

    notes_start = 2 + len(examples) + 1
    notes = [
        "How to use this template:",
        "• Replace the example rows above with your own keywords — one per row.",
        "• Keyword: the search term you want to track (required).",
        "• You don't need to enter any rank — SEO Dashboard finds each keyword's current position automatically the next time you run “Check rankings”.",
        "• Keep the header row. Delete these notes if you like.",
        "• Up to %d keywords per file." % MAX_ROWS,
    ]
    for i, line in enumerate(notes):
        cell = ws.cell(row=notes_start + i, column=1)
        cell.value = line
        cell.font = Font(name="Arial", italic=True, color="78716C", bold=(i == 0))

    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def parse_keyword_workbook(file_bytes: bytes) -> tuple[list[dict], list[dict]]:
    try:
        wb = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception:
        raise ValueError("That file couldn't be read as an Excel (.xlsx) workbook.")

    ws = wb.active
    valid: list[dict] = []
    errors: list[dict] = []
    seen_terms: set[str] = set()
    data_rows = 0

    for excel_row, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if excel_row == 1:
            continue
        if row is None:
            continue

        term_raw = row[0] if len(row) > 0 else None

        if term_raw is None or str(term_raw).strip() == "":
            continue

        if isinstance(term_raw, str) and term_raw.strip().startswith(("How to use", "•")):
            continue

        data_rows += 1
        if data_rows > MAX_ROWS:
            errors.append({"row": excel_row, "reason": f"File exceeds the {MAX_ROWS}-keyword limit; remaining rows ignored."})
            break

        term = str(term_raw).strip().lower()

        if term in seen_terms:
            errors.append({"row": excel_row, "reason": f"Duplicate of an earlier row for “{term}”; skipped."})
            continue
        seen_terms.add(term)

        valid.append({"term": term})

    return valid, errors
