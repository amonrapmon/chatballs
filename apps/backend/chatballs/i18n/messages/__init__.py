"""Backend message catalogues for supported languages."""

from __future__ import annotations

from chatballs.i18n.messages import (
    assistance_en,
    assistance_ru,
    comments_en,
    comments_ru,
    diagnostics_en,
    diagnostics_ru,
    en,
    ru,
    transfers_en,
    transfers_ru,
)

CATALOG: dict[str, dict[str, object]] = {
    "ru": {
        **ru.MESSAGES,
        **transfers_ru.MESSAGES,
        **diagnostics_ru.MESSAGES,
        **comments_ru.MESSAGES,
        **assistance_ru.MESSAGES,
    },
    "en": {
        **en.MESSAGES,
        **transfers_en.MESSAGES,
        **diagnostics_en.MESSAGES,
        **comments_en.MESSAGES,
        **assistance_en.MESSAGES,
    },
}

__all__ = ["CATALOG"]
