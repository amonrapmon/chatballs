"""Ошибки настроек внешнего сервера: собираются все сразу, по полям.

Форма HTTP-запроса показывает все ошибки разом (SPEC-0023 R-8), поэтому
проверка не останавливается на первой.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError

from chatballs.i18n import t


class SettingsErrors:
    def __init__(self) -> None:
        self._by_field: dict[str, list[str]] = {}

    def add(self, field: str, key: str, /, **params: object) -> None:
        self.add_text(field, t(key, **params))

    def add_text(self, field: str, text: str) -> None:
        self._by_field.setdefault(field, []).append(text)

    def raise_if_any(self) -> None:
        if self._by_field:
            raise ValidationError(self._by_field)
