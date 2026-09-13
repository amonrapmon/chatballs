from django.conf import settings
from django.db.models import Sum
from django.utils import timezone

from chatballs.ai.models import LlmInvocation, LlmInvocationStatus


class LimitExceeded(Exception):
    pass


def _day_start():
    now = timezone.localtime()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def daily_cost_micros(channel=None) -> int:
    queryset = LlmInvocation.objects.filter(created_at__gte=_day_start(), status=LlmInvocationStatus.SUCCESS)
    if channel is not None:
        queryset = queryset.filter(channel=channel)
    return queryset.aggregate(total=Sum("cost_micros"))["total"] or 0


def assert_within_limits() -> None:
    """Единственный лимит расхода — общий по установке, из переменной окружения.

    Дневного бюджета на агенте нет: он считался по прайс-таблице, где всего две
    модели, и на любой другой расход оставался нулевым — лимит не срабатывал
    никогда и давал ложное чувство защиты.
    """

    global_limit = settings.CHATBALLS_AI_GLOBAL_DAILY_COST_LIMIT_MICROS
    if global_limit and daily_cost_micros() >= global_limit:
        raise LimitExceeded("Global daily AI cost limit reached")
