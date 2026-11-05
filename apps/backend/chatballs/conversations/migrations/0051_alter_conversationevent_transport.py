"""Align API Connector transport choice display labels with TextChoices.

Migration 0049 already expanded the column to 16 characters and updated the
database CHECK constraint. This state-only change reconciles the historical
migration's uppercase choice labels with ConversationEventTransport.choices.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0050_connector_operator_delivery")]

    operations = [
        migrations.AlterField(
            model_name="conversationevent",
            name="transport",
            field=models.CharField(
                blank=True,
                null=True,
                max_length=16,
                choices=[
                    ("MAX", "Max"),
                    ("TELEGRAM", "Telegram"),
                    ("VK", "Vk"),
                    ("WEB", "Web"),
                    ("EMAIL", "Email"),
                    ("API_CONNECTOR", "Api Connector"),
                ],
            ),
        ),
    ]
