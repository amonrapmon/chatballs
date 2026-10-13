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
    observations_en,
    observations_ru,
    participants_en,
    participants_ru,
    quality_en,
    quality_ru,
    ru,
    template_variables_en,
    template_variables_ru,
    transfers_en,
    transfers_ru,
    work_status_en,
    work_status_ru,
)

CATALOG: dict[str, dict[str, object]] = {
    "ru": {
        **ru.MESSAGES,
        **participants_ru.MESSAGES,
        **transfers_ru.MESSAGES,
        **diagnostics_ru.MESSAGES,
        **comments_ru.MESSAGES,
        **assistance_ru.MESSAGES,
        **work_status_ru.MESSAGES,
        **template_variables_ru.MESSAGES,
        **observations_ru.MESSAGES,
        **quality_ru.MESSAGES,
    },
    "en": {
        **en.MESSAGES,
        **participants_en.MESSAGES,
        **transfers_en.MESSAGES,
        **diagnostics_en.MESSAGES,
        **comments_en.MESSAGES,
        **assistance_en.MESSAGES,
        **work_status_en.MESSAGES,
        **template_variables_en.MESSAGES,
        **observations_en.MESSAGES,
        **quality_en.MESSAGES,
    },
}

__all__ = ["CATALOG"]
