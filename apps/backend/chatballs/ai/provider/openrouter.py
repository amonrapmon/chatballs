from chatballs.ai.provider import openai_http
from chatballs.ai.provider.base import ChatMessage, ChatResult, EmbeddingResult, LLMProvider
from chatballs.i18n import t


class OpenRouterProvider(LLMProvider):
    """OpenRouter HTTP adapter (stdlib only).

    OpenAI Chat Completions shape with usage.include=true (returns the actual
    USD cost in usage.cost). Delegates HTTP/parsing to the shared openai_http
    layer (ADR-CHATBALLS-0034 §3); this adapter only carries the
    OpenRouter product semantics (cost reporting). Exercised with a real key;
    tests use the LocalProvider.
    """

    name = "openrouter"

    def __init__(self, *, api_key: str, base_url: str, timeout: float = 30.0, proxy_url: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.proxy_url = proxy_url or ""

    def chat(self, *, messages: list[ChatMessage], model: str, params: dict | None = None) -> ChatResult:
        return openai_http.chat_completions(
            base_url=self.base_url, api_key=self.api_key, messages=messages, model=model,
            timeout=self.timeout, proxy_url=self.proxy_url, params=params,
        )

    def embed(self, *, texts: list[str], model: str) -> list[EmbeddingResult]:
        return openai_http.embeddings(
            base_url=self.base_url, api_key=self.api_key, texts=texts, model=model,
            timeout=self.timeout, proxy_url=self.proxy_url,
        )

    def transcribe(self, *, audio: bytes, filename: str, content_type: str, model: str) -> str:
        # OpenAI-совместимый POST /audio/transcriptions (whisper). Формат ответа
        # {"text": "..."}; ошибки транслируются в ProviderError.
        #
        # Наружу уходит фраза для человека, а не ответ провайдера: оператору
        # в ленте сообщений нечего делать с JSON чужого API. Сам ответ пишется
        # в журнал — по нему разбирают настройку.
        import json
        import logging
        import urllib.error
        import urllib.request

        from chatballs.ai.provider.base import ProviderError
        from chatballs.conversations.transports.base import multipart_body
        from chatballs.integrations.proxy import build_opener

        logger = logging.getLogger(__name__)

        body, body_type = multipart_body(
            {"model": model},
            file_field="file",
            filename=filename,
            content=audio,
            content_type=content_type,
        )
        request = urllib.request.Request(
            self.base_url.rstrip("/") + "/audio/transcriptions",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": body_type,
            },
            method="POST",
        )
        try:
            with build_opener(self.proxy_url).open(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:300]
            logger.warning(
                "Transcription rejected by %s: HTTP %s %s (model=%s)",
                self.base_url,
                error.code,
                detail,
                model,
            )
            # 401/403 — ключ или доступ; 404 — у провайдера нет эндпоинта
            # расшифровки (так отвечают Anthropic и Yandex Foundation Models);
            # остальное — временный отказ, который лечится повтором.
            if error.code in (401, 403):
                raise ProviderError(t("ai.transcription_denied")) from error
            if error.code == 404:
                raise ProviderError(t("ai.transcription_unsupported")) from error
            raise ProviderError(t("ai.transcription_failed")) from error
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            logger.warning("Transcription request to %s failed: %s", self.base_url, error)
            raise ProviderError(t("ai.transcription_unreachable")) from error
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ProviderError(t("ai.empty_transcript"))
        return text
