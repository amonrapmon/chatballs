"""Внешний сервер (SPEC-0023 R-1): род интеграции, виды MCP и HTTP и
зашифрованная колонка под секретные заголовки."""

from django.db import migrations, models

import chatballs.identity.crypto


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0010_integration_runtime_revision"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integration",
            name="kind",
            field=models.CharField(
                choices=[
                    ("LLM_PROVIDER", "LLM-провайдер"),
                    ("MESSENGER", "Подключение-мессенджер"),
                    ("EXTERNAL_SERVER", "Внешний сервер"),
                ],
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="integration",
            name="provider",
            field=models.CharField(
                choices=[
                    ("OPENROUTER", "OpenRouter"),
                    ("CUSTOM", "Custom (OpenAI-compatible)"),
                    ("DEMO", "Демо-провайдер (без ключа)"),
                    ("MAX", "MAX"),
                    ("TELEGRAM", "Telegram"),
                    ("VK", "ВКонтакте"),
                    ("WEB", "Web-виджет"),
                    ("EMAIL", "Email (IMAP/SMTP)"),
                    ("MCP", "MCP-сервер"),
                    ("HTTP", "HTTP-запрос"),
                ],
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="integration",
            name="secret_headers",
            field=chatballs.identity.crypto.EncryptedCharField(blank=True, max_length=87480),
        ),
    ]
