"""Псевдонимизация текстов для модели (ADR-0031, SPEC-0022 R-2–R-6).

Перед вызовом провайдера персональные значения заменяются токенами вида
``[[...]]``, а в ответе модели токены заменяются обратно на значения.

Карта «токен → значение» живёт только в экземпляре ``Pseudonymizer`` и только
в памяти хода (R-6): его нельзя сохранять, сериализовать и писать в журнал.
Один экземпляр обслуживает все тексты хода — вопрос для эмбеддинга, системные
блоки, знания, историю, — поэтому одно значение всегда получает один токен.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from itertools import count
from typing import NamedTuple

from chatballs.ai.pii import EMAIL_PATTERN, LONG_DIGITS_PATTERN, PHONE_PATTERN

CLIENT_NAME = "client_name"
CLIENT_EMAIL = "client_email"
CLIENT_PHONE = "client_phone"

# Между цифрами известного телефона допускается то же, что и в шаблоне телефона.
_PHONE_GAP = r"[\s().-]*"

# Токен в ответе модели и его обломки. Тройная скобка — это скобка из текста
# рядом с токеном («[Анна]» → «[[[client_name]]]»), а не начало токена.
_TOKEN = re.compile(
    r"\[\[(?!\[)(?P<name>[^\[\]\n]{0,80})\]\]"
    r"|\[\[(?!\[)[\w-]*\]?"
    r"|(?:\[|(?<![\w-]))[\w-]*\]\]"
)


@dataclass(frozen=True, slots=True)
class KnownValue:
    """Известное значение хода: имя токена без скобок и само значение."""

    token: str
    value: str = field(repr=False)
    is_phone: bool = False


class Restored(NamedTuple):
    """Ответ с подставленными значениями и число удалённых токенов."""

    text: str
    removed: int


def contact_known_values(*, name: str = "", email: str = "", phone: str = "") -> list[KnownValue]:
    return [
        KnownValue(CLIENT_NAME, name),
        KnownValue(CLIENT_EMAIL, email),
        KnownValue(CLIENT_PHONE, phone, is_phone=True),
    ]


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _text_key(text: str) -> str:
    return " ".join(text.split()).casefold()


def _wrap(name: str) -> str:
    return f"[[{name}]]"


def _known_pattern(value: str, *, is_phone: bool) -> str:
    if is_phone:
        return r"(?<![\w+])\+?" + _PHONE_GAP.join(_digits(value)) + r"(?!\w)"
    return r"(?<!\w)" + r"\s+".join(re.escape(part) for part in value.split()) + r"(?!\w)"


def _candidates(base: str, *, numbered: bool) -> Iterator[str]:
    if not numbered:
        yield base
    yield from (f"{base}_{number}" for number in count(1 if numbered else 2))


class Pseudonymizer:
    """Карта одного хода: маскирует тексты для модели и восстанавливает ответ."""

    __slots__ = ("_known_groups", "_pattern", "_tokens", "_values")

    def __init__(self, known: Iterable[KnownValue] = ()) -> None:
        self._values: dict[str, str] = {}  # имя токена → значение
        self._tokens: dict[str, str] = {}  # нормализованное значение → имя токена
        self._known_groups: dict[str, str] = {}  # группа шаблона → имя токена
        known_parts: list[tuple[int, str]] = []
        for item in known:
            value = str(item.value or "").strip()
            is_phone = item.is_phone and bool(_digits(value))
            key = _digits(value) if is_phone else _text_key(value)
            # Пустое значение маскировать нечем; повтор значения под другим
            # именем уже получает первый токен.
            if not key or key in self._tokens:
                continue
            # Ключ своего поля может совпасть с занятым именем токена.
            name = self._free_name(item.token, numbered=False)
            self._values[name] = value
            self._tokens[key] = name
            group = f"known_{len(self._known_groups)}"
            self._known_groups[group] = name
            pattern = _known_pattern(value, is_phone=is_phone)
            known_parts.append((len(value), f"(?P<{group}>{pattern})"))
        # При общем начале выигрывает более длинное известное значение.
        known_parts.sort(key=lambda part: -part[0])
        # Один проход слева направо: вставленный токен повторно не разбирается.
        # E-mail идёт раньше известных значений, чтобы имя не откусило начало
        # чужого адреса; свой адрес при этом узнаётся по карте.
        self._pattern = re.compile(
            "|".join([
                f"(?P<email>{EMAIL_PATTERN.pattern})",
                *(part for _, part in known_parts),
                f"(?P<number>{LONG_DIGITS_PATTERN.pattern})",
                f"(?P<phone>{PHONE_PATTERN.pattern})",
                r"(?P<open>\[(?=\[))",
                r"(?P<close>\](?=\]))",
            ]),
            re.IGNORECASE,
        )

    def __repr__(self) -> str:
        return f"<Pseudonymizer tokens={len(self._values)}>"

    def __reduce__(self):
        raise TypeError("Pseudonymizer keeps turn values in memory only and is not serializable")

    def mask(self, text: str) -> str:
        """Заменить значения токенами и экранировать чужие ``[[...]]`` (R-2–R-4)."""
        if not text:
            return text
        return self._pattern.sub(self._mask_match, text)

    def restore(self, text: str) -> Restored:
        """Подставить значения вместо токенов хода, остальные токены удалить (R-5)."""
        removed = 0

        def replace(match: re.Match[str]) -> str:
            nonlocal removed
            value = self._values.get(match.group("name") or "")
            if value is None:
                removed += 1
                return ""
            return value

        if not text:
            return Restored(text, 0)
        return Restored(_TOKEN.sub(replace, text), removed)

    def _mask_match(self, match: re.Match[str]) -> str:
        group = match.lastgroup or ""
        raw = match.group()
        # Пробел между скобками: в тексте для модели пара «[[» бывает только
        # у токенов этого хода, подделать токен текстом нельзя.
        if group in ("open", "close"):
            return raw + " "
        if group in self._known_groups:
            return _wrap(self._known_groups[group])
        if group == "email":
            # Шаблон захватывает точку в конце предложения — она не часть адреса.
            value = raw.rstrip(".-")
            return _wrap(self._numbered(group, _text_key(value), value)) + raw[len(value):]
        return _wrap(self._numbered(group, _digits(raw), raw))

    def _numbered(self, kind: str, key: str, value: str) -> str:
        name = self._tokens.get(key)
        if name is None:
            name = self._free_name(kind, numbered=True)
            self._tokens[key] = name
            self._values[name] = value
        return name

    def _free_name(self, base: str, *, numbered: bool) -> str:
        return next(
            name for name in _candidates(base, numbered=numbered) if name not in self._values
        )
