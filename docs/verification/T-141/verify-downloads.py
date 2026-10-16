"""Read the actual browser downloads, supplied as base64 JSON on stdin."""

import base64
import csv
import json
import sys
from io import BytesIO, StringIO

from openpyxl import load_workbook

payload = json.load(sys.stdin)
csv_rows = list(csv.reader(StringIO(base64.b64decode(payload["csv"]).decode("utf-8-sig"))))
workbook = load_workbook(BytesIO(base64.b64decode(payload["xlsx"])), data_only=False)
assert all(cell.data_type != "f" for sheet in workbook for row in sheet for cell in row)
rating_sheet = workbook["Сводка клиентских оценок"]
ratings = [row for row in list(rating_sheet.values)[1:] if row[0] == "totals"]
assert [row[5] for row in ratings] == [4.5, 2]
assert [row[4] for row in ratings] == [2, 1]
assert [(row[7], row[8], row[9]) for row in ratings] == [(2, 2, 1), (2, 1, 0.5)]
quality = [row for row in list(workbook["Сводка качества"].values)[1:] if row[0] == "totals"]
assert len(quality) == 7
tone = next(row for row in quality if row[3] == 3 and row[9] == "tone")
assert (tone[18], tone[19], tone[15]) == (5, 8, 1)
unscored = next(row for row in quality if row[3] == 3 and row[9] == "resolution")
assert unscored[14] == 1
unused = next(row for row in quality if row[3] == 1)
assert unused[6] == 0 and isinstance(unused[19], str)
index = csv_rows.index(["Сводка клиентских оценок"])
csv_totals = [row for row in csv_rows[index + 2:index + 4] if row[0] == "totals"]
assert [float(row[5]) for row in csv_totals] == [row[5] for row in ratings]
assert [float(row[9]) for row in csv_totals] == [row[9] for row in ratings]
index = csv_rows.index(["Сводка качества"])
csv_quality = csv_rows[index + 2:index + 9]
assert len(csv_quality) == 7
assert [row[9] for row in csv_quality] == [row[9] for row in quality]
for csv_row, xlsx_row in zip(csv_quality, quality, strict=True):
    assert (float(csv_row[19]) == xlsx_row[19] if isinstance(xlsx_row[19], (int, float))
            else csv_row[19] == xlsx_row[19])
print(json.dumps({"browserDownloads": True, "ratingScales": 2, "qualityCriteria": 7,
                  "csvXlsxMatch": True, "formulaCells": 0, "testRecords": True}))
