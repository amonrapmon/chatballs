"""File rendering only: no queries or independent calculations."""

import csv
from io import BytesIO, StringIO

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from chatballs.conversations.support_export_rows import report_tables
from chatballs.i18n import t


def safe_csv_value(value):
    if value is None:
        return t("support_stats.unavailable")
    if isinstance(value, str):
        first = next((char for char in value if not char.isspace() and ord(char) >= 32), "")
        if first in {"=", "+", "-", "@"} or value.startswith(("\t", "\r", "\n")):
            return "'" + value
    return value


def export_csv(report):
    output = StringIO(newline="")
    writer = csv.writer(output)
    for name, rows in report_tables(report):
        writer.writerow([t(f"support_stats.sheet.{name}")])
        writer.writerows([safe_csv_value(value) for value in row] for row in rows)
        writer.writerow([])
    return output.getvalue().encode("utf-8-sig")


def export_xlsx(report):
    workbook = Workbook(write_only=True)
    for name, rows in report_tables(report):
        sheet = workbook.create_sheet(t(f"support_stats.sheet.{name}"))
        for row in rows:
            cells = []
            for value in row:
                if isinstance(value, str):
                    value = ILLEGAL_CHARACTERS_RE.sub("", value)
                cell = WriteOnlyCell(sheet, value=t("support_stats.unavailable") if value is None else value)
                if isinstance(cell.value, str):
                    # Explicit string type disables formulas on every sheet.
                    cell.data_type = "s"
                cells.append(cell)
            sheet.append(cells)
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()
