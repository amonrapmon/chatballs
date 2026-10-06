"""Очистка HTML текста согласия (SPEC-0020 R-14–R-15).

Текст согласия пишет администратор, а показывает виджет на чужом сайте,
поэтому разметка проходит белый список. Чужие теги удаляются с сохранением
текста, ``script`` и ``style`` — вместе с содержимым, атрибуты — все, кроме
``href`` у ссылки. Ссылка без разрешённой схемы (в том числе относительная)
теряет ``href``. Переносы строк в ``<br>`` не превращаются.
"""

from __future__ import annotations

import nh3

_TAGS = {"a", "strong", "b", "em", "i", "u", "br", "p", "ul", "ol", "li"}
_URL_SCHEMES = {"http", "https", "mailto", "tel"}
_LINK_REL = "noopener noreferrer nofollow"


def clean_consent_html(text: str) -> str:
    return nh3.clean(
        text,
        tags=_TAGS,
        clean_content_tags={"script", "style"},
        attributes={"a": {"href"}},
        url_schemes=_URL_SCHEMES,
        url_relative="deny",
        link_rel=_LINK_REL,
        set_tag_attribute_values={"a": {"target": "_blank"}},
    ).strip()
