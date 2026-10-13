from django.apps import AppConfig


class RatingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "chatballs.ratings"

    def ready(self):
        from chatballs.ratings import scheduling  # noqa: F401
