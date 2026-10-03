import re

# Минимизация данных перед LLM (ADR-CHATBALLS-0011): email, телефоны, длинные
# числовые идентификаторы (карты/платежи/заказы) не передаются в модель.
# Те же правила находит слой псевдонимизации (chatballs.ai.pseudonymization).
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LONG_DIGITS_PATTERN = re.compile(r"\b\d[\d\s-]{10,}\d\b")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")


def redact(text: str) -> str:
    if not text:
        return text
    text = EMAIL_PATTERN.sub("[email]", text)
    text = LONG_DIGITS_PATTERN.sub("[number]", text)
    text = PHONE_PATTERN.sub("[phone]", text)
    return text
