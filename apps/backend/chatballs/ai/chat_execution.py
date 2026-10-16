"""Provider calls and retries share the absolute turn deadline."""

import time
from copy import copy

from django.conf import settings

from chatballs.ai.provider.base import ProviderRejected
from chatballs.ai.provider.breakers import breaker_for
from chatballs.ai.provider.resilience import call_with_resilience


def run_chat(job):
    def remaining():
        if job.deadline is None:
            return None
        left = job.deadline - time.monotonic()
        if left <= 0:
            raise ProviderRejected("turn deadline passed")
        return left

    def invoke():
        from chatballs.ai.execution_policy import check_execution

        check_execution()
        left = remaining()
        provider = job.provider
        if left is not None and hasattr(provider, "timeout"):
            provider = copy(provider)
            provider.timeout = min(provider.timeout, left)
        tools = {"tools": job.tools} if job.tools else {}
        result = provider.chat(messages=job.messages, model=job.model, params=job.params, **tools)
        return result

    def sleep(delay):
        left = remaining()
        if left is not None and delay >= left:
            raise ProviderRejected("turn deadline passed")
        time.sleep(delay)

    return call_with_resilience(
        invoke, retries=settings.CHATBALLS_AI_MAX_RETRIES,
        breaker=breaker_for(job.breaker_key, job.breaker_revision), sleep=sleep,
    )
