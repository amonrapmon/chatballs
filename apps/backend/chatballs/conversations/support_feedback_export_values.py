import json

from chatballs.i18n import t


def feedback_value(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else value


def feedback_table(columns):
    return [[t(f"support_stats.feedback.{key}") for key in columns]]
