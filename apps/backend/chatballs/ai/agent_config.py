from django.db import models

# Границы окна истории агента (AIAgent.history_limit).
HISTORY_LIMIT_DEFAULT = 20
HISTORY_LIMIT_MAX = 200


class AnswerLanguage(models.TextChoices):
    """Режимы поля ``AIAgent.answer_language``, кроме кодов самих языков."""

    MIRROR = "MIRROR", "Как у клиента"
    ORGANIZATION = "ORGANIZATION", "Язык организации"


class AIAgentStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ACTIVE = "ACTIVE", "Active"
    DISABLED = "DISABLED", "Disabled"
    ARCHIVED = "ARCHIVED", "Archived"
