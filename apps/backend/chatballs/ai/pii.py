import re

# Минимизация данных перед LLM (ADR-CHATBALLS-0011): email, телефоны, длинные
# числовые идентификаторы (карты/платежи/заказы) не передаются в модель.
# По этим правилам слой псевдонимизации (chatballs.ai.pseudonymization)
# заменяет значения токенами и возвращает их в ответ модели.
EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
LONG_DIGITS_PATTERN = re.compile(r"\b\d[\d\s-]{10,}\d\b")
PHONE_PATTERN = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
