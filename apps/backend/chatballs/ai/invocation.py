import time

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

_breaker = CircuitBreaker()


def _prepare_invocation(*, channel, requested_model: str | None) -> tuple[LLMProvider, str]:
    # BYOK — единственный режим (ADR-CHATBALLS-0042 §3): модель берётся из интеграции
    # организации с fallback на модель агента. Без интеграции модель остаётся
    # агентской: тестовый провайдер работает, прод упадёт в get_provider штатно.
    agent = channel.ai_agent
    try:
        effective_model = routing.resolve_model(channel, fallback_model=agent.model)
    except routing.IntegrationNotConfigured:
        effective_model = agent.model
    return get_provider(channel=channel), requested_model or effective_model


def invoke_chat(
    *,
    channel,
    messages: list[ChatMessage],
    purpose: str,
    model: str | None = None,
    params: dict | None = None,
    used_fragment_ids: list | None = None,
) -> ChatResult:
    provider, model = _prepare_invocation(channel=channel, requested_model=model)

    safe_messages = [ChatMessage(role=item.role, content=redact(item.content)) for item in messages]
    started = time.monotonic()
    try:
        result: ChatResult = call_with_resilience(
            lambda: provider.chat(messages=safe_messages, model=model, params=params),
            retries=settings.CHATBALLS_AI_MAX_RETRIES,
            breaker=_breaker,
        )
    except ProviderError as error:
        LlmInvocation.objects.create(
            organization=channel.organization,
            channel=channel,
            purpose=purpose,
            operation="chat",
            model=model,
            status=LlmInvocationStatus.ERROR,
            error=str(error)[:1000],
            latency_ms=int((time.monotonic() - started) * 1000),
        )
        raise

    return_result = result
    LlmInvocation.objects.create(
        organization=channel.organization,
        channel=channel,
        purpose=purpose,
        operation="chat",
        model=result.model,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        latency_ms=int((time.monotonic() - started) * 1000),
        status=LlmInvocationStatus.SUCCESS,
        used_fragment_ids=used_fragment_ids or [],
    )
    return return_result


def embed_texts(
    *,
    channel=None,
    organization=None,
    texts: list[str],
    model: str,
    purpose: str = "retrieval",
) -> list[EmbeddingResult]:
    provider = get_provider(channel=channel)
    results: list[EmbeddingResult] = call_with_resilience(
        lambda: provider.embed(texts=texts, model=model),
        retries=settings.CHATBALLS_AI_MAX_RETRIES,
        breaker=_breaker,
    )
    tokens = sum(result.tokens for result in results)
    LlmInvocation.objects.create(
        organization=channel.organization if channel else organization,
        channel=channel,
        purpose=purpose,
        operation="embedding",
        model=model,
        prompt_tokens=tokens,
        total_tokens=tokens,
        status=LlmInvocationStatus.SUCCESS,
    )
    return results
