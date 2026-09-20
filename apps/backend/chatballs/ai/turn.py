"""Ход агента по шагам: транзакция — сеть — транзакция — сеть — транзакция.

Ответ клиенту складывается из двух обращений к провайдеру (вектор вопроса и
сам ответ) и нескольких обращений к базе между ними. Сделанные подряд, они
держат транзакцию организации открытой всё время ожидания провайдера — а это
минуты (chatballs.ai.invocation). Здесь работа разложена так, чтобы каждое
обращение к базе шло своей короткой транзакцией, а походы наружу оставались
между ними.

Порядок шагов у вызывающего (chatballs.conversations.ai_turn):

1. в транзакции: `plan_query_embedding`
2. вне транзакции: `run_query_embedding`
3. в транзакции: `plan_chat`
4. вне транзакции: `run_turn_chat`
5. в транзакции: `record_turn` и запись ответа

Шаги `run_*` ошибок провайдера не поднимают: отказ — это такой же результат
хода, его пишут в журнал и разбирают в диалоге (передачей оператору).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from django.conf import settings

from chatballs.ai.invocation import (
    ChatJob,
    EmbeddingJob,
    prepare_chat,
    prepare_embedding,
    record_chat,
    record_embedding,
    run_chat,
    run_embedding,
)
from chatballs.ai.models import AIAgent
from chatballs.ai.provider.base import ChatResult, EmbeddingResult, ProviderError
from chatballs.ai.retrieval import merge_hits
from chatballs.ai.runtime import build_turn_messages

FRAGMENT_LIMIT = 5


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


@dataclass(frozen=True, slots=True)
class QueryEmbedding:
    """Вектор вопроса. Пустой вектор — обычное дело: остаётся лексический поиск."""

    vector: list[float] | None = None
    model: str = ""
    latency_ms: int = 0
    results: list[EmbeddingResult] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TurnPlan:
    """Готовый запрос к модели и то, на чём он основан."""

    job: ChatJob
    fragment_ids: list[int]


@dataclass(frozen=True, slots=True)
class TurnAnswer:
    """Итог похода к модели: либо ответ, либо отказ, и сколько это заняло."""

    result: ChatResult | None = None
    error: ProviderError | None = None
    latency_ms: int = 0


def plan_query_embedding(*, agent: AIAgent, query: str) -> EmbeddingJob | None:
    """Шаг в транзакции: чем считать вектор вопроса. None — считать нечем."""

    if not query.strip():
        return None
    try:
        return prepare_embedding(
            channel=agent.channel,
            texts=[query],
            model=settings.CHATBALLS_AI_EMBEDDING_MODEL,
            timeout=settings.CHATBALLS_AI_TURN_TIMEOUT,
        )
    except ProviderError:
        # Провайдера нет или он не настроен: семантический поиск необязателен.
        return None


def run_query_embedding(job: EmbeddingJob | None) -> QueryEmbedding:
    """Шаг без транзакции: обращение к провайдеру за вектором."""

    if job is None:
        return QueryEmbedding()
    started = time.monotonic()
    try:
        results = run_embedding(job)
    except ProviderError:
        # Знания найдутся лексическим поиском; ход из-за этого не срывается.
        return QueryEmbedding(latency_ms=_elapsed_ms(started))
    return QueryEmbedding(
        vector=results[0].vector if results else None,
        model=job.model,
        latency_ms=_elapsed_ms(started),
        results=results,
    )


def plan_chat(
    *,
    agent: AIAgent,
    message: str,
    history: list[dict] | None = None,
    embedding: QueryEmbedding | None = None,
    style_guard: bool = True,
) -> TurnPlan:
    """Шаг в транзакции: поиск знаний, сборка промпта и выбор модели.

    Заодно здесь оседает журнальная строка о векторе вопроса: считали его
    снаружи транзакции, а писать её всё равно в базу.
    """
    embedding = embedding or QueryEmbedding()
    if embedding.results:
        record_embedding(
            channel=agent.channel,
            model=embedding.model,
            purpose="retrieval_query",
            results=embedding.results,
            latency_ms=embedding.latency_ms,
        )
    fragments = merge_hits(agent, message, embedding.vector, limit=FRAGMENT_LIMIT)
    job = prepare_chat(
        channel=agent.channel,
        messages=build_turn_messages(
            agent=agent,
            message=message,
            history=history,
            fragments=fragments,
            style_guard=style_guard,
        ),
        model=agent.model,
        params=agent.model_params or None,
        timeout=settings.CHATBALLS_AI_TURN_TIMEOUT,
    )
    return TurnPlan(job=job, fragment_ids=[fragment.id for fragment in fragments])


def run_turn_chat(plan: TurnPlan) -> TurnAnswer:
    """Шаг без транзакции: обращение к модели за ответом."""

    started = time.monotonic()
    try:
        result = run_chat(plan.job)
    except ProviderError as error:
        return TurnAnswer(error=error, latency_ms=_elapsed_ms(started))
    return TurnAnswer(result=result, latency_ms=_elapsed_ms(started))


def record_turn(*, agent: AIAgent, plan: TurnPlan, answer: TurnAnswer) -> None:
    """Шаг в транзакции: строка журнала вызовов — и об ответе, и об отказе."""

    record_chat(
        channel=agent.channel,
        job=plan.job,
        purpose="agent_chat",
        result=answer.result,
        error=answer.error,
        latency_ms=answer.latency_ms,
        used_fragment_ids=plan.fragment_ids,
    )
