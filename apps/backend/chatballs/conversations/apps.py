from django.apps import AppConfig


class ConversationsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    label = "conversations"
    name = "chatballs.conversations"
    verbose_name = "Conversations (contacts, dialogs, messages)"

    def import_models(self) -> None:
        super().import_models()
        from chatballs.conversations.quality import models  # noqa: F401

    def ready(self) -> None:
        from chatballs.conversations.quality import worker  # noqa: F401
        # Свежесть диалога поддерживает сигнал: сообщения создаются в семи местах.
        from chatballs.conversations import (
            event_handlers,  # noqa: F401  (register outbox handlers)
            signals,  # noqa: F401
        )
