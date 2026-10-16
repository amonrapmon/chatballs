"""Bounded RFC Message-ID header parsing for SMTP and inbound routing."""

import re

_MESSAGE_ID = re.compile(r"<[^<>\s]+@[^<>\s]+>")


def message_ids(value):
    values = value if isinstance(value, list) else [value]
    return [item for value in values for item in _MESSAGE_ID.findall(str(value)) if len(item) <= 998][-30:]
