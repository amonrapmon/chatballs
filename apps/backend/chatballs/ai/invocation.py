"""Обращения к LLM-провайдеру: подготовка, сам вызов и запись в журнал.

Вызов провайдера ждёт ответа десятки секунд, а подготовка и журнал — это
обращения к базе. В одной функции они означают открытую транзакцию на всё время
ожидания, а вместе с ней занятое соединение из пула и RLS-контекст
(chatballs.tenancy.middleware). Поэтому шаги разделены: `prepare_*` и `record_*`
вызывают внутри транзакции, `run_*` — вне её.

`invoke_chat` и `embed_texts` остаются для мест, где ждать под транзакцией не
жалко: индексация знаний, предпросмотр карточки агента, тесты. Ход диалога с
клиентом ходит по шагам (chatballs.ai.turn).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from django.conf import settings

from chatballs.ai.models import LlmInvocation, LlmInvocationStatus
from chatballs.ai.pii import redact
from chatballs.ai.provider import routing
from chatballs.ai.provider.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    LLMProvider,
    ProviderError,
)
from chatballs.ai.provider.factory import get_provider
from chatballs.ai.provider.resilience import CircuitBreaker, call_with_resilience

# Предохранитель считает сбои по ключу «организация + интеграция»: провайдер у
# каждой организации свой, и отозванный ключ одной не имеет отношения к AI
# остальных. Общий на процесс предохранитель гасил AI у всех сразу.
_breakers: dict[tuple[int, int], CircuitBreaker] = {}


def _breaker(key: tuple[int, int]) -> CircuitBreaker:
    breaker = _breakers.get(key)
    if breaker is None:
        breaker = CircuitBreaker()
        _breakers[key] = breaker
    return breaker


def reset_breakers() -> None:
    """Для тестов: забыть накопленные сбои провайдеров."""

    _breakers.clear()


def _breaker_key(channel) -> tuple[int, int]:
    """Ключ предохранителя. Без канала провайдер может быть только тестовым —
    считать сбои там не по чему, и общий ключ (0, 0) никому не мешает."""

    if channel is None:
        return (0, 0)
    return (channel.organization_id, routing.integration_id(channel))


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


@dataclass(frozen=True, slots=True)
class ChatJob:
    """Всё для похода к модели, уже прочитанное из базы."""

    provider: LLMProvider
    model: str
    messages: list[ChatMessage]
    breaker_key: tuple[int, int]
    params: dict | None = None


@dataclass(frozen=True, slots=True)
class EmbeddingJob:
    """То же для эмбеддингов: вектор считается тем же провайдером организации."""

    provider: LLMProvider
    model: str
    texts: list[str]
    breaker_key: tuple[int, int]


def _effective_model(channel, requested_model: str | None) -> str:
    # BYOK — единственный режим (ADR-CHATBALLS-0042 §3): модель берётся из интеграции
    # организации с fallback на модель агента. Без интеграции модель остаётся
    # агентской: тестовый провайдер работает, прод упадёт в get_provider штатно.
    agent = getattr(channel, "ai_agent", None)
    fallback = str(getattr(agent, "model", "") or "")
    if requested_model:
        return requested_model
    try:
        return routing.resolve_model(channel, fallback_model=fallback)
    except routing.IntegrationNotConfigured:
        return fallback


def prepare_chat(
    *,
    channel,
    messages: list[ChatMessage],
    model: str | None = None,
    params: dict | None = None,
    timeout: float | None = None,
) -> ChatJob:
    """Шаг в транзакции: провайдер, модель и очищенный от ПДн текст запроса."""

    return ChatJob(
        provider=get_provider(channel=channel, timeout=timeout),
        model=_effective_model(channel, model),
        messages=[ChatMessage(role=item.role, content=redact(item.content)) for item in messages],
        breaker_key=_breaker_key(channel),
        params=params,
    )


def run_chat(job: ChatJob) -> ChatResult:
    """Шаг без транзакции: обращение к провайдеру."""

    return call_with_resilience(
        lambda: job.provider.chat(messages=job.messages, model=job.model, params=job.params),
        retries=settings.CHATBALLS_AI_MAX_RETRIES,
        breaker=_breaker(job.breaker_key),
    )


def record_chat(
    *,
    channel,
    job: ChatJob,
    purpose: str,
    result: ChatResult | None = None,
    error: Exception | None = None,
    latency_ms: int = 0,
    used_fragment_ids: list | None = None,
) -> None:
    """Шаг в транзакции: строка журнала вызовов — и об успехе, и об отказе."""

    LlmInvocation.objects.create(
        organization=channel.organization,
        channel=channel,
        purpose=purpose,
        operation="chat",
        model=result.model if result is not None else job.model,
        prompt_tokens=result.prompt_tokens if result else 0,
        completion_tokens=result.completion_tokens if result else 0,
        total_tokens=result.total_tokens if result else 0,
        latency_ms=latency_ms,
        status=LlmInvocationStatus.SUCCESS if result is not None else LlmInvocationStatus.ERROR,
        error="" if error is None else str(error)[:1000],
        used_fragment_ids=used_fragment_ids or [],
    )


def invoke_chat(
    *,
    channel,
    messages: list[ChatMessage],
    purpose: str,
    model: str | None = None,
    params: dict | None = None,
    used_fragment_ids: list | None = None,
) -> ChatResult:
    """Три шага подряд, в транзакции вызывающего: там, где ждать не жалко."""

    job = prepare_chat(channel=channel, messages=messages, model=model, params=params)
    started = time.monotonic()
    try:
        result = run_chat(job)
    except ProviderError as error:
        record_chat(
            channel=channel,
            job=job,
            purpose=purpose,
            error=error,
            latency_ms=_elapsed_ms(started),
        )
        raise
    record_chat(
        channel=channel,
        job=job,
        purpose=purpose,
        result=result,
        latency_ms=_elapsed_ms(started),
        used_fragment_ids=used_fragment_ids,
    )
    return result


def prepare_embedding(
    *,
    channel,
    texts: list[str],
    model: str,
    timeout: float | None = None,
) -> EmbeddingJob:
    """Шаг в транзакции: провайдер эмбеддингов организации."""

    return EmbeddingJob(
        provider=get_provider(channel=channel, timeout=timeout),
        model=model,
        texts=texts,
        breaker_key=_breaker_key(channel),
    )


def run_embedding(job: EmbeddingJob) -> list[EmbeddingResult]:
    """Шаг без транзакции: обращение к провайдеру."""

    return call_with_resilience(
        lambda: job.provider.embed(texts=job.texts, model=job.model),
        retries=settings.CHATBALLS_AI_MAX_RETRIES,
        breaker=_breaker(job.breaker_key),
    )


def record_embedding(
    *,
    channel=None,
    organization=None,
    model: str,
    purpose: str,
    results: list[EmbeddingResult],
    latency_ms: int = 0,
) -> None:
    """Шаг в транзакции: строка журнала."""

    tokens = sum(result.tokens for result in results)
    LlmInvocation.objects.create(
        organization=channel.organization if channel else organization,
        channel=channel,
        purpose=purpose,
        operation="embedding",
        model=model,
        prompt_tokens=tokens,
        total_tokens=tokens,
        latency_ms=latency_ms,
        status=LlmInvocationStatus.SUCCESS,
    )


def embed_texts(
    *,
    channel=None,
    organization=None,
    texts: list[str],
    model: str,
    purpose: str = "retrieval",
) -> list[EmbeddingResult]:
    """Три шага подряд: индексация знаний и прочие неинтерактивные места."""

    job = prepare_embedding(channel=channel, texts=texts, model=model)
    started = time.monotonic()
    results = run_embedding(job)
    record_embedding(
        channel=channel,
        organization=organization,
        model=model,
        purpose=purpose,
        results=results,
        latency_ms=_elapsed_ms(started),
    )
    return results
