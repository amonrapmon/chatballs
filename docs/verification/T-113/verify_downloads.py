"""Verify actual browser files against its native API JSON; stdin is base64 JSON."""
import base64
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone
from decimal import Decimal
from io import BytesIO, StringIO

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "chatballs_backend.settings_admin")
import django

django.setup()
from openpyxl import load_workbook
from chatballs.conversations.support_export import safe_csv_value
from chatballs.conversations.support_export_rows import report_tables
from chatballs.i18n import t

payload = json.load(sys.stdin)
tables = report_tables(payload["report"])
generated = t("support_stats.generated")


def canonical(value):
    # JSON renders dates in the selected timezone; files preserve UTC offsets.
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T.+", value):
        return datetime.fromisoformat(value).astimezone(timezone.utc).isoformat()
    if isinstance(value, str) and re.fullmatch(r"-?\d+(\.\d+)?([eE][+-]?\d+)?", value):
        return Decimal(value)
    return value


def stable(rows):
    # Separate requests have separate generation instants.
    return [[canonical(value) for value in row] for row in rows if not row or row[0] != generated]


expected_csv = []
for name, rows in tables:
    expected_csv.append([t(f"support_stats.sheet.{name}")])
    expected_csv.extend([[str(safe_csv_value(value)) for value in row] for row in rows])
    expected_csv.append([])
actual_csv = list(csv.reader(StringIO(base64.b64decode(payload["csv"]).decode("utf-8-sig"))))
expected_stable, actual_stable = stable(expected_csv), stable(actual_csv)
if expected_stable != actual_stable:
    differences = [(index, expected, actual) for index, (expected, actual)
                   in enumerate(zip(expected_stable, actual_stable)) if expected != actual]
    raise AssertionError(f"Downloaded CSV differs: lengths {len(expected_stable)}/{len(actual_stable)}, first {differences[:3]}")
book = load_workbook(BytesIO(base64.b64decode(payload["xlsx"])), data_only=False)
assert len(book.worksheets) == len(tables), "Unexpected sheet count"
for sheet, (name, rows) in zip(book, tables, strict=True):
    expected = [[t("support_stats.unavailable") if value is None else None if value == "" else value
                 for value in row] for row in rows]
    assert sheet.title == t(f"support_stats.sheet.{name}"), "Unexpected sheet title"
    assert stable(expected) == stable([list(row) for row in sheet.values]), f"Sheet {name} differs"
    assert not any(cell.data_type == "f" for row in sheet for cell in row), "Unexpected formula"
print(f"Browser API/CSV/XLSX match: {len(tables)} tables; values, units, coverage, filters and details.")
