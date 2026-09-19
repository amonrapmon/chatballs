"""Gateway messenger integration type."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0009_integration_vk"),
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
                    ("GATEWAY", "Gateway"),
                ],
                max_length=16,
            ),
        ),
    ]
