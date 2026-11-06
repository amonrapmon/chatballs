"""Join API Connector and 1.20 service-connection migrations."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0015_api_connector_provider"),
        ("integrations", "0033_merge_speech_and_native"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integration",
            name="kind",
            field=models.CharField(
                choices=[
                    ("LLM_PROVIDER", "LLM-провайдер"),
                    ("SPEECH_PROVIDER", "Речевой провайдер"),
                    ("MESSENGER", "Подключение-мессенджер"),
                    ("EXTERNAL_SERVER", "Внешний сервер"),
                    ("SERVICE", "Сервис"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="integration",
            name="provider",
            field=models.CharField(
                choices=[
                    ("YANDEX_SPEECHKIT", "Yandex SpeechKit"),
                    ("OPENROUTER", "OpenRouter"),
                    ("CUSTOM", "Custom (OpenAI-compatible)"),
                    ("DEMO", "Демо-провайдер (без ключа)"),
                    ("MAX", "MAX"),
                    ("TELEGRAM", "Telegram"),
                    ("VK", "ВКонтакте"),
                    ("WEB", "Web-виджет"),
                    ("EMAIL", "Email (IMAP/SMTP)"),
                    ("API_CONNECTOR", "API Connector"),
                    ("MCP", "MCP-сервер"),
                    ("HTTP", "HTTP-запрос"),
                    ("ADAPTER", "Адаптер сервиса"),
                ],
                max_length=16,
            ),
        ),
    ]
