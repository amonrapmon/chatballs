"""Предзаполнение первого открытия настроек по утверждённому кадру N10.

Это предложение настроек: оно не записывается в БД и не включает опрос.
Клиентский текст берётся на языке организации, а не открывшего форму сотрудника.
"""

from chatballs.i18n import t


def settings_defaults(language):
    return {
        "scale": [{"value": value, "label": t(f"ratings.default_label_{value}", language=language)}
                  for value in range(1, 6)],
        "text": t("ratings.default_request", language=language),
        "delaySeconds": 600,
    }
