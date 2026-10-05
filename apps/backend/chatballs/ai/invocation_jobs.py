"""Подготовленные задания провайдеру, передаваемые за границу транзакции."""

from dataclasses import dataclass

from chatballs.ai.provider.base import ChatMessage, LLMProvider, ToolSpec


@dataclass(frozen=True, slots=True)
class ChatJob:
    """Всё для похода к модели, уже прочитанное из базы."""

    provider: LLMProvider
    model: str
    messages: list[ChatMessage]
    breaker_key: tuple[int, int]
    breaker_revision: int
    params: dict | None = None
    # Инструменты хода (chatballs.ai.tool_loop); без них запрос обычный.
    tools: list[ToolSpec] | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingJob:
    """То же для эмбеддингов: вектор считается тем же провайдером организации."""

    provider: LLMProvider
    model: str
    texts: list[str]
    breaker_key: tuple[int, int]
    breaker_revision: int
