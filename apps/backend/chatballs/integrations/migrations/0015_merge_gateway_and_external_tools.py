from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        (
            "integrations",
            "0011_merge_0010_integration_gateway_0010_integration_runtime_revision",
        ),
        ("integrations", "0014_merge_field_access_and_tools"),
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
                    ("MCP", "MCP-сервер"),
                    ("HTTP", "HTTP-запрос"),
                ],
                max_length=16,
            ),
        ),
    ]
