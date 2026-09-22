from django.test import SimpleTestCase

from chatballs.ai.invocation import _breaker, reset_breakers
from chatballs.ai.provider.base import ProviderError
from chatballs.ai.provider.resilience import (
    CircuitBreaker,
    CircuitBreakerOpen,
    call_with_resilience,
)


class ProviderResilienceTests(SimpleTestCase):
    def test_retries_count_as_one_logical_failure(self) -> None:
        breaker = CircuitBreaker(failure_threshold=2, reset_timeout=999)
        calls = {"n": 0}

        def always_fail():
            calls["n"] += 1
            raise ProviderError("down")

        for _ in range(2):
            with self.assertRaises(ProviderError):
                call_with_resilience(
                    always_fail,
                    retries=2,
                    breaker=breaker,
                    sleep=lambda _s: None,
                )
        self.assertEqual(calls["n"], 6)
        with self.assertRaises(CircuitBreakerOpen):
            call_with_resilience(always_fail, retries=2, breaker=breaker)
        self.assertEqual(calls["n"], 6)

    def test_circuit_breaker_allows_probe_after_cooldown(self) -> None:
        now = [0.0]
        breaker = CircuitBreaker(
            failure_threshold=1,
            reset_timeout=30,
            clock=lambda: now[0],
        )

        def fail():
            raise ProviderError("down")

        with self.assertRaises(ProviderError):
            call_with_resilience(fail, retries=0, breaker=breaker)
        now[0] = 29
        with self.assertRaises(CircuitBreakerOpen):
            call_with_resilience(lambda: "ok", retries=0, breaker=breaker)
        now[0] = 30
        self.assertEqual(
            call_with_resilience(lambda: "ok", retries=0, breaker=breaker),
            "ok",
        )

    def test_runtime_revision_replaces_open_breaker(self) -> None:
        reset_breakers()
        self.addCleanup(reset_breakers)
        first = _breaker((1, 2), revision=1)
        for _ in range(first.failure_threshold):
            first.on_failure()
        with self.assertRaises(CircuitBreakerOpen):
            first.before()

        second = _breaker((1, 2), revision=2)
        self.assertIsNot(second, first)
        second.before()
