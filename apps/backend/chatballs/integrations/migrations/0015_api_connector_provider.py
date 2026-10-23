"""Register API Connector as a vendor-neutral Integration provider."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("integrations", "0014_merge_field_access_and_tools")]

    operations = [
        migrations.AlterField(
            model_name="integration",
            name="provider",
            field=models.CharField(
                max_length=16,
                choices=[
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
                ],
            ),
        ),
    ]
