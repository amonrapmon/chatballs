"""Shared HTTP layer for OpenAI-compatible LLM providers (ADR-CHATBALLS-0034 §3).



The OpenRouter and generic Custom providers both

speak the same Chat Completions shape:



- POST /chat/completions with {model, messages, ...}; response has

  choices[0].message.content and usage (prompt/completion tokens).

- POST /embeddings with {model, input}; response has data[].embedding and usage.

- Authorization: Bearer <key>.



This module owns the HTTP transport and response parsing so the adapters

do not duplicate it. Adapters stay responsible for their own product semantics

(name, catalog). Stdlib only — no third-party HTTP client.

"""



from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

from chatballs.ai.provider.base import (
    ChatMessage,
    ChatResult,
    EmbeddingResult,
    ProviderError,
    ProviderRejected,
)
from chatballs.i18n import t
from chatballs.integrations.proxy import build_opener


def post_json(*, base_url: str, path: str, api_key: str, payload: dict, timeout: float, proxy_url: str = "") -> dict:

    """POST a JSON body to {base_url}{path} with Bearer auth; return parsed JSON.



    Translates transport errors into ProviderError so callers can apply the

    circuit breaker uniformly.

    """

    request = urllib.request.Request(

        f"{base_url.rstrip('/')}{path}",

        data=json.dumps(payload).encode("utf-8"),

        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},

        method="POST",

    )

    try:

        with build_opener(proxy_url).open(request, timeout=timeout) as response:

            return json.loads(response.read().decode("utf-8"))

    # Отказ самого провайдера разбирается отдельно: 4xx (кроме 429) — это ключ,

    # модель или размер запроса, и повтор даст тот же ответ через ещё один таймаут.

    except urllib.error.HTTPError as error:

        detail = error.read().decode("utf-8", "replace")[:300]

        if error.code != 429 and 400 <= error.code < 500:

            raise ProviderRejected(f"HTTP {error.code}: {detail}") from error

        raise ProviderError(f"HTTP {error.code}: {detail}") from error

    # http.client.HTTPException covers IncompleteRead/BadStatusLine (dropped reply)

    # — those are not OSError, so they would slip past ProviderError otherwise.

    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as error:

        raise ProviderError(f"{type(error).__name__}: {error}") from error





def get_json(*, base_url: str, path: str, api_key: str, timeout: float, proxy_url: str = "") -> dict:

    """GET {base_url}{path} with Bearer auth; return parsed JSON (used for /models)."""

    request = urllib.request.Request(

        f"{base_url.rstrip('/')}{path}",

        headers={"Authorization": f"Bearer {api_key}"},

        method="GET",

    )

    try:

        with build_opener(proxy_url).open(request, timeout=timeout) as response:

            body = response.read().decode("utf-8")

            return json.loads(body) if body else {}

    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException, json.JSONDecodeError) as error:

        raise ProviderError(f"{type(error).__name__}: {error}") from error





def chat_completions(*, base_url: str, api_key: str, messages: list[ChatMessage], model: str,

                     timeout: float, proxy_url: str = "", params: dict | None = None) -> ChatResult:

    """POST /chat/completions and parse the OpenAI-shaped response."""

    payload: dict = {

        "model": model,

        "messages": [{"role": m.role, "content": m.content} for m in messages],

        **(params or {}),

    }

    data = post_json(base_url=base_url, path="/chat/completions", api_key=api_key,

                     payload=payload, timeout=timeout, proxy_url=proxy_url)

    try:

        text = data["choices"][0]["message"]["content"]

    except (KeyError, IndexError, TypeError) as error:

        raise ProviderError(t("ai.unexpected_provider_response", error=error)) from error

    usage = data.get("usage") or {}

    return ChatResult(

        text=text,

        model=data.get("model", model),

        prompt_tokens=int(usage.get("prompt_tokens", 0)),

        completion_tokens=int(usage.get("completion_tokens", 0)),

    )





def embeddings(*, base_url: str, api_key: str, texts: list[str], model: str,

               timeout: float, proxy_url: str = "") -> list[EmbeddingResult]:

    """POST /embeddings and parse the OpenAI-shaped response."""

    data = post_json(base_url=base_url, path="/embeddings", api_key=api_key,

                     payload={"model": model, "input": texts}, timeout=timeout, proxy_url=proxy_url)

    try:

        items = data["data"]

    except (KeyError, TypeError) as error:

        raise ProviderError(t("ai.unexpected_provider_response", error=error)) from error

    usage = data.get("usage") or {}

    per_text = int(usage.get("prompt_tokens", 0)) // max(1, len(texts))

    return [EmbeddingResult(vector=item["embedding"], model=data.get("model", model), tokens=per_text) for item in items]

