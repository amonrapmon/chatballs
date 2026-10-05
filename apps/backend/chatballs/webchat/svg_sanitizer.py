"""Очистка SVG-иконки виджета.

Иконка кнопки и шапки показывается на чужих сайтах и отдаётся с адреса
приложения, поэтому SVG чистится до сохранения. В отличие от логотипа
организации (``identity.logo_svg``) файл не отклоняется целиком: опасное
вырезается, картинка остаётся.

Удаляется: элементы вне пространства имён SVG, script, foreignObject и
встраиваемые iframe/embed/object/audio/video; атрибуты-обработчики on*;
href и xlink:href, которые ведут не на якорь ``#``; любые значения с
javascript:/vbscript:/data:text; анимации, подменяющие ссылки и обработчики;
стили с @import, expression и внешними url(). Отклоняется то, что очистить
нельзя: не XML, не SVG, DOCTYPE и сущности.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

SVG_NAMESPACE = "http://www.w3.org/2000/svg"
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"

# Без регистрации ElementTree пишет ns0:svg. Параметр default_namespace не
# подходит: он требует пространство имён и у атрибутов.
ET.register_namespace("", SVG_NAMESPACE)
ET.register_namespace("xlink", XLINK_NAMESPACE)

_REMOVED_TAGS = frozenset(
    {"script", "foreignobject", "iframe", "embed", "object", "audio", "video"}
)
_ANIMATION_TAGS = frozenset({"animate", "set", "animatemotion", "animatetransform"})
_DECLARATION = re.compile(rb"<!\s*(DOCTYPE|ENTITY)", re.IGNORECASE)
_EXTERNAL_URL = re.compile(r"url\(\s*['\"]?\s*(?!#)", re.IGNORECASE)
_UNSAFE_SCHEMES = ("javascript:", "vbscript:", "data:text")


class UnsafeSvg(ValueError):
    """SVG не разбирается или не может быть очищен."""


def _local(name: str) -> str:
    return name.rsplit("}", 1)[-1].lower()


def _namespace(name: str) -> str:
    return name[1:].split("}", 1)[0] if name.startswith("{") else ""


def _compact(value: str) -> str:
    return re.sub(r"[\s\x00-\x1f]+", "", value).lower()


def _unsafe_value(value: str) -> bool:
    compact = _compact(value)
    return any(scheme in compact for scheme in _UNSAFE_SCHEMES)


def _unsafe_css(text: str) -> bool:
    compact = _compact(text)
    return "@import" in compact or "expression(" in compact or bool(_EXTERNAL_URL.search(text))


def _unsafe_attribute(name: str, value: str) -> bool:
    local = _local(name)
    if local.startswith("on") or _unsafe_value(value):
        return True
    if local == "href":
        return not value.strip().startswith("#")
    return local == "style" and _unsafe_css(value)


def _unsafe_animation(element: ET.Element) -> bool:
    target = _local(element.get("attributeName", ""))
    return target == "href" or target.startswith("on")


def _removed(element: ET.Element) -> bool:
    tag = element.tag if isinstance(element.tag, str) else ""
    if _namespace(tag) != SVG_NAMESPACE:
        return True
    local = _local(tag)
    if local in _REMOVED_TAGS:
        return True
    if local in _ANIMATION_TAGS and _unsafe_animation(element):
        return True
    return local == "style" and _unsafe_css(element.text or "")


def _qualify(root: ET.Element) -> None:
    """SVG без xmlns браузер в <img> не рисует: переводим его в пространство SVG."""

    for element in root.iter():
        if isinstance(element.tag, str) and not element.tag.startswith("{"):
            element.tag = f"{{{SVG_NAMESPACE}}}{element.tag}"


def _clean(element: ET.Element) -> None:
    for child in list(element):
        if _removed(child):
            element.remove(child)
        else:
            _clean(child)
    for name in [name for name, value in element.attrib.items() if _unsafe_attribute(name, value)]:
        del element.attrib[name]


def sanitize_svg(data: bytes) -> bytes:
    if _DECLARATION.search(data):
        raise UnsafeSvg("DOCTYPE and entities are not allowed")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise UnsafeSvg("SVG is not well-formed XML") from error
    _qualify(root)
    if not isinstance(root.tag, str) or root.tag != f"{{{SVG_NAMESPACE}}}svg":
        raise UnsafeSvg("Root element is not svg")
    _clean(root)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
