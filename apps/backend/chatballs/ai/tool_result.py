"""Результат инструмента для модели: текст с токенами вместо ПДн (SPEC-0023 R-12).

Ответ обрезается до 256 КБ, JSON приводится к компактному виду и проходит тот
же слой псевдонимизации, что и остальной текст хода. Шаблоны узнают e-mail,
телефоны и длинные числа, а ФИО и адрес в свободном тексте — нет (SPEC-0022,
вне рамок). Поэтому в JSON они узнаются по ключу: значение под ключом, похожим
на имя человека или адрес, заменяется токеном целиком. ФИО и адрес под другим
ключом или в обычном тексте уходят модели как есть — осознанный компромисс.
"""

from __future__ import annotations

import json
import re

from chatballs.ai.pseudonymization import Pseudonymizer

MAX_RESULT_BYTES = 256 * 1024

NAME = "name"
ADDRESS = "address"

_WORD = re.compile(r"[A-ZА-ЯЁ]?[a-zа-яё]+|[A-ZА-ЯЁ]+(?![a-zа-яё])")
_NAME_WORDS = frozenset({
    "fio", "fullname", "firstname", "lastname", "middlename", "surname", "patronymic",
    "фио", "фамилия", "отчество",
})
_NAME_QUALIFIERS = frozenset({"full", "first", "last", "middle", "second", "given", "family"})
# О ком речь: «name» рядом с таким словом — имя человека, а не товара.
_PERSON_WORDS = frozenset({
    "customer", "client", "buyer", "user", "contact", "person", "recipient", "receiver",
    "addressee", "owner", "payer", "courier", "driver",
    "клиент", "покупатель", "получатель", "заказчик", "курьер",
})
_ADDRESS_WORDS = frozenset({
    "address", "addr", "street", "city", "zip", "zipcode", "postcode", "postal", "apartment",
    "адрес", "улица", "город", "квартира",
})


def _forms(word: str) -> tuple[str, str]:
    # «customers» — список тех же людей.
    word = word.casefold()
    return word, word.removesuffix("s")


def _words(key: str) -> set[str]:
    return {form for word in _WORD.findall(key) for form in _forms(word)}


def _names_a_person(key: str) -> bool:
    """Ключ целиком о человеке: «customer», «recipient»."""
    found = _WORD.findall(key)
    return bool(found) and all(_PERSON_WORDS.intersection(_forms(word)) for word in found)


def _key_kind(key: str, parent: str) -> str | None:
    """Что лежит под ключом: имя человека, адрес или None — обычное значение."""
    words = _words(key)
    if words & _ADDRESS_WORDS or any("address" in word or "адрес" in word for word in words):
        return ADDRESS
    if words & _NAME_WORDS or _names_a_person(key):
        return NAME
    if words & {"name", "имя"} and (words | _words(parent)) & (_PERSON_WORDS | _NAME_QUALIFIERS):
        return NAME
    # «customername», «clientName» одним словом.
    if any(word.removesuffix("name") in _PERSON_WORDS for word in words if word.endswith("name")):
        return NAME
    return None


def _mask(value: object, pseudonymizer: Pseudonymizer, kind: str | None, parent: str) -> object:
    if isinstance(value, dict):
        return {
            pseudonymizer.mask(str(key)): _mask(
                item,
                pseudonymizer,
                # Части адреса — адрес; у человека же внутри не только имя.
                _key_kind(str(key), parent) or (kind if kind == ADDRESS else None),
                str(key),
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_mask(item, pseudonymizer, kind, parent) for item in value]
    if value is None or isinstance(value, bool):
        return value
    if kind:
        return pseudonymizer.tokenize(kind, str(value))
    if isinstance(value, str):
        return pseudonymizer.mask(value)
    # Число: длинный идентификатор или телефон, записанный числом.
    text = str(value)
    masked = pseudonymizer.mask(text)
    return value if masked == text else masked


def _truncated(text: str) -> str:
    raw = text.encode("utf-8")
    if len(raw) <= MAX_RESULT_BYTES:
        return text
    return raw[:MAX_RESULT_BYTES].decode("utf-8", errors="ignore")


def masked_result(text: str, pseudonymizer: Pseudonymizer) -> str:
    """Текст результата под маской карты хода."""
    text = _truncated(text)
    try:
        data = json.loads(text)
    except ValueError:
        return pseudonymizer.mask(text)
    if not isinstance(data, dict | list):
        return pseudonymizer.mask(text)
    masked = _mask(data, pseudonymizer, None, "")
    return json.dumps(masked, ensure_ascii=False, separators=(",", ":"))
