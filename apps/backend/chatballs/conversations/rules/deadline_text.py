"""Срок ответа словами — для текста, который правило отправляет клиенту.

Организация пишет текст сама и помечает место срока. Число минут из настройки
подставляется словами на языке организации: «15 минут», «2 часа», «1 час
30 минут». Метка своя у каждого языка интерфейса, а при отправке узнаётся любая
из них: текст могли набрать, когда язык был другим.
"""

from __future__ import annotations

from chatballs.i18n import LANGUAGE_CODES, t, tn


def placeholder(language: str | None = None) -> str:
    """Метка срока на языке читателя — для подсказки в настройке."""
    return "{" + t("rules.deadline_placeholder", language=language) + "}"


def duration_text(minutes: int, language: str) -> str:
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(tn("rules.duration_hours", hours, language=language))
    if rest or not hours:
        parts.append(tn("rules.duration_minutes", rest, language=language))
    return " ".join(parts)


def render(text: str, minutes: int, language: str) -> str:
    """Текст клиенту: метки срока заменены сроком, остальное — как написано."""
    deadline = duration_text(minutes, language)
    for code in LANGUAGE_CODES:
        text = text.replace(placeholder(code), deadline)
    return text
