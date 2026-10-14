import base64
import csv
import json
import sys
from io import BytesIO, StringIO
from openpyxl import load_workbook

payload = json.load(sys.stdin)
allowed = set(payload['allowed'])
rows = list(csv.reader(StringIO(base64.b64decode(payload['csv']).decode('utf-8-sig'))))
start = rows.index(['Доступность истории статусов']) + 2
csv_ids = set()
for row in rows[start:]:
    if not row:
        break
    csv_ids.add(int(row[0]))
book = load_workbook(BytesIO(base64.b64decode(payload['xlsx'])), read_only=True)
xlsx_ids = {int(row[0]) for row in list(book['Доступность истории статусов'].values)[1:]}
assert csv_ids == allowed == xlsx_ids, (csv_ids, xlsx_ids, allowed)
assert not any(cell.data_type == 'f' for sheet in book for row in sheet for cell in row)
print(json.dumps({'csvEmployees': sorted(csv_ids), 'xlsxEmployees': sorted(xlsx_ids), 'formulaCells': 0}))
