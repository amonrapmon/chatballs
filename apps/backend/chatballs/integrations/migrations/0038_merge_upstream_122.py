"""Rejoin upstream 1.22 provider history with API Connector and Gateway fork history.

Both branches apply their own provider AlterField; preserve all choices in
migration state rather than silently dropping fork-only providers.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0037_merge_upstream_121"),
        ("integrations", "0036_web_schema_generation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integration",
            name="provider",
            field=models.CharField(
                max_length=16,
                choices=[
                    ("YANDEX_SPEECHKIT", "Yandex SpeechKit"),
                    ("OPENAI", "OpenAI"),
                    ("OPENROUTER", "OpenRouter"),
                    ("CUSTOM", "Custom (OpenAI-compatible)"),
                    ("DEMO", "Демо-провайдер (без ключа)"),
                    ("MAX", "MAX"),
                    ("TELEGRAM", "Telegram"),
                    ("VK", "ВКонтакте"),
                    ("WEB", "Web-виджет"),
                    ("EMAIL", "Email (IMAP/SMTP)"),
                    ("API_CONNECTOR", "API Connector"),
                    ("GATEWAY", "Gateway"),
                    ("MCP", "MCP-сервер"),
                    ("HTTP", "HTTP-запрос"),
                    ("ADAPTER", "Адаптер сервиса"),
                ],
            ),
        ),
    ]
