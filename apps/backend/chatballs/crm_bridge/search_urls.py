"""CRM links refer to filtered client search results, never to a direct profile."""

from __future__ import annotations

import re
from urllib.parse import urlencode


_COMPANY_ID = re.compile(r"[0-9]+\Z")
_ALLOWED_PHONE_PUNCTUATION = frozenset("+()-. /\t\r\n\u00a0")


def normalize_phone(phone: str | None) -> str | None:
    """Keep ASCII digits only; never infer or rewrite an international prefix."""
    if not isinstance(phone, str) or not phone.strip():
        return None
    if any(not ("0" <= char <= "9" or char in _ALLOWED_PHONE_PUNCTUATION) for char in phone):
        return None
    digits = "".join(char for char in phone if "0" <= char <= "9")
    if not (7 <= len(digits) <= 15) or set(digits) == {"0"}:
        return None
    return digits


def build_client_search_url(
    provider: str, external_company_id: str | int, phone: str | None
) -> str | None:
    """Return a pre-filtered CRM search URL, or None when inputs are unusable."""
    company_id = str(external_company_id).strip()
    digits = normalize_phone(phone)
    if not _COMPANY_ID.fullmatch(company_id) or digits is None:
        return None
    if provider == "DIKIDI":
        params = urlencode((("company", company_id), ("filter", "username"), ("query", digits)))
        return f"https://dikidi.net/ru/owner/clients/?{params}"
    if provider == "YCLIENTS":
        params = urlencode((
            ("filters[0][operation]", "OR"),
            ("filters[1][type]", "quick_search"),
            ("filters[1][state][value]", digits),
        ))
        return f"https://yclients.ru/clients/{company_id}/base?{params}"
    return None
