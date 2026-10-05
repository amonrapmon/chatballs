"""Обращения к LLM-провайдеру: подготовка, сам вызов и запись в журнал.

Вызов провайдера ждёт ответа десятки секунд, а подготовка и журнал — это
обращения к базе. В одной функции они означают открытую транзакцию на всё время
ожидания, а вместе с ней занятое соединение из пула и RLS-контекст
(chatballs.tenancy.middleware). Поэтому шаги разделены: `prepare_*` и `record_*`
вызывают внутри транзакции, `run_*` — вне её.

`invoke_chat` и `embed_texts` остаются для мест, где ждать под транзакцией не
жалко: индексация знаний, предпросмотр карточки агента, тесты. Ход диалога с
клиентом ходит по шагам (chatballs.ai.turn).

Персональные значения до провайдера не доходят (SPEC-0022 R-1): `prepare_*`
заменяют их токенами карты хода (chatballs.ai.pseudonymization), `restore_reply`
возвращает значения в ответ модели. Сама карта остаётся у вызывающего и в
журнал вызовов не попадает.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, replace

from django.conf import settings

from chatballs.ai.models import LlmInvocation, LlmInvocationStatus
from chatballs.ai.provider import routing
from chatballs.ai.provider.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    LLMProvider,
    ProviderError,
    ToolSpec,
)
from chatballs.ai.provider.breakers import breaker_for, breaker_identity
from chatballs.ai.provider.factory import get_provider
from chatballs.ai.provider.resilience import call_with_resilience
from chatballs.ai.pseudonymization import Pseudonymizer

logger = logging.getLogger(__name__)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


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
    pseudonymizer: Pseudonymizer,
    model: str | None = None,
    params: dict | None = None,
    timeout: float | None = None,
) -> ChatJob:
    """Шаг в транзакции: провайдер, модель и текст запроса с токенами вместо ПДн."""

    breaker_key, breaker_revision = breaker_identity(channel)
    return ChatJob(
        provider=get_provider(channel=channel, timeout=timeout),
        model=_effective_model(channel, model),
        messages=[
            item
            if item.masked
            else ChatMessage(role=item.role, content=pseudonymizer.mask(item.content))
            for item in messages
        ],
        breaker_key=breaker_key,
        breaker_revision=breaker_revision,
        params=params,
    )


def run_chat(job: ChatJob) -> ChatResult:
    """Шаг без транзакции: обращение к провайдеру."""

    tools = {"tools": job.tools} if job.tools else {}
    return call_with_resilience(
        lambda: job.provider.chat(
            messages=job.messages, model=job.model, params=job.params, **tools
        ),
        retries=settings.CHATBALLS_AI_MAX_RETRIES,
        breaker=breaker_for(job.breaker_key, job.breaker_revision),
    )


def restore_reply(*, channel, pseudonymizer: Pseudonymizer, text: str) -> str:
    """Ответ модели с настоящими значениями вместо токенов хода (SPEC-0022 R-5).

    Неизвестные и искажённые токены удаляются. В журнал уходит только их число:
    ни значений, ни самих токенов там быть не должно.
    """
    restored = pseudonymizer.restore(text)
    if restored.removed:
        logger.warning(
            "Removed %s unknown or malformed pseudonymization tokens from the model reply"
            " (channel %s)",
            restored.removed,
            getattr(channel, "id", None),
        )
    return restored.text


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
    pseudonymizer: Pseudonymizer | None = None,
) -> ChatResult:
    """Три шага подряд, в транзакции вызывающего: там, где ждать не жалко.

    Ответ возвращается уже с подставленными значениями. Без своей карты хода
    известных значений нет, маскируется только найденное шаблонами.
    """
    if pseudonymizer is None:
        pseudonymizer = Pseudonymizer()
    job = prepare_chat(
        channel=channel,
        messages=messages,
        pseudonymizer=pseudonymizer,
        model=model,
        params=params,
    )
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
    return replace(
        result,
        text=restore_reply(channel=channel, pseudonymizer=pseudonymizer, text=result.text),
    )


def prepare_embedding(
    *,
    channel,
    texts: list[str],
    model: str,
    timeout: float | None = None,
    pseudonymizer: Pseudonymizer | None = None,
) -> EmbeddingJob:
    """Шаг в транзакции: провайдер эмбеддингов организации.

    Вопрос клиента приходит сюда с картой хода и уходит провайдеру под маской.
    Знания при индексации идут без карты: это тексты организации, а не клиента.
    """
    breaker_key, breaker_revision = breaker_identity(channel)
    if pseudonymizer is not None:
        texts = [pseudonymizer.mask(text) for text in texts]
    return EmbeddingJob(
        provider=get_provider(channel=channel, timeout=timeout),
        model=model,
        texts=texts,
        breaker_key=breaker_key,
        breaker_revision=breaker_revision,
    )


def run_embedding(job: EmbeddingJob) -> list[EmbeddingResult]:
    """Шаг без транзакции: обращение к провайдеру."""

    return call_with_resilience(
        lambda: job.provider.embed(texts=job.texts, model=job.model),
        retries=settings.CHATBALLS_AI_MAX_RETRIES,
        breaker=breaker_for(job.breaker_key, job.breaker_revision),
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
    pseudonymizer: Pseudonymizer | None = None,
) -> list[EmbeddingResult]:
    """Три шага подряд: индексация знаний и прочие неинтерактивные места."""

    job = prepare_embedding(
        channel=channel, texts=texts, model=model, pseudonymizer=pseudonymizer
    )
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
