"""Очистка своего CSS виджета (SPEC-0021 R-7).

CSS вставляется ``<style>`` внутри iframe чата. Сервер вырезает то, чем из
стилей можно подгрузить чужое или выполнить код: ``@import``, ``url(...)`` с
внешним адресом и ``expression(...)``. CSP страницы чата — второй рубеж, а не
единственный.
"""

import re

# Экранирование буквы (``\\69`` → «i», ``\\m`` → «m») браузер раскрывает до
# разбора, и ``@\\69mport`` работает как ``@import``. Раскрываем только буквы:
# экраны цифр и знаков (``.\\31 23``, ``.hover\\:x``) значимы для селекторов.
_HEX_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})[ \t\r\n\f]?")
_LETTER_ESCAPE = re.compile(r"\\([g-zG-Z])")

_IMPORT = re.compile(r"""@import(?:"[^"\n]*"?|'[^'\n]*'?|[^;{}\n"'])*;?""", re.IGNORECASE)
_EXPRESSION = re.compile(r"expression\s*\([^)]*\)?", re.IGNORECASE)
_URL = re.compile(
    r"""url\(\s*("(?:[^"\\\n]|\\.)*"?|'(?:[^'\\\n]|\\.)*'?|[^)]*?)\s*(?:\)|$)""",
    re.IGNORECASE,
)
# Пробелы и управляющие символы парсер адресов выкидывает: «/\t/evil» — это «//evil».
_URL_NOISE = re.compile(r"[\x00-\x20\x7f]")
_SCHEME = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)


def _unescape_letters(css: str) -> str:
    def hex_letter(match: re.Match) -> str:
        code = int(match.group(1), 16)
        char = chr(code) if code < 0x80 else ""
        return char if char.isalpha() else match.group(0)

    return _LETTER_ESCAPE.sub(r"\1", _HEX_ESCAPE.sub(hex_letter, css))


def _is_local_url(raw: str) -> bool:
    """Адрес не уводит за пределы страницы чата: якорь, путь или data:image."""
    target = _URL_NOISE.sub("", raw.strip("\"'"))
    if "\\" in target:
        return False
    if target.startswith("//"):
        return False
    if _SCHEME.match(target):
        return target.lower().startswith("data:image/")
    return True


def sanitize_custom_css(css: str) -> str:
    css = _unescape_letters(css)
    css = _IMPORT.sub("", css)
    css = _EXPRESSION.sub("", css)
    css = _URL.sub(lambda match: match.group(0) if _is_local_url(match.group(1)) else "", css)
    # Закрывающий </style> не должен выйти из тега, как бы виджет ни вставлял CSS.
    return css.replace("<", "\\3c ")
