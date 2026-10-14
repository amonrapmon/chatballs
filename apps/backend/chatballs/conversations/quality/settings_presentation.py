"""Editor choices; stored criteria remain independent immutable snapshots."""

import json

from chatballs.i18n import t


def criteria_value_literals(criteria):
    return {row["code"]: [json.dumps(value, ensure_ascii=False) for value in row["scale"]] for row in criteria}


def scale_catalog():
    return [
        {"id": "yes_no", "label": t("quality.scale_binary"),
         "values": [t("quality.scale_no"), t("quality.scale_yes")]},
        {"id": "one_five", "label": t("quality.scale_five"), "values": list(range(1, 6))},
        {"id": "zero_ten", "label": t("quality.scale_ten"), "values": list(range(11))},
    ]
