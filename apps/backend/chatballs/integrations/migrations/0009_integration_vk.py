"""Подключение-сообщество ВКонтакте: новое значение provider (choices)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0008_encrypted_column_width"),
    ]

    operations = [
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
                ],
                max_length=16,
            ),
        ),
    ]
