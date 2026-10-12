"""Internal delivery status for a Gateway AI reply suppressed before dispatch."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0032_merge_gateway_and_participant_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="delivery_status",
            field=models.CharField(
                blank=True, max_length=32, default="",
                choices=[
                    ("", "Не задано"),
                    ("queued", "В очереди"),
                    ("suppressed", "Suppressed before delivery"),
                    ("provider_accepted", "Принято провайдером"),
                    ("delivered", "Доставлено"),
                    ("read", "Прочитано"),
                    ("failed", "Ошибка доставки"),
                    ("no_account", "Аккаунт не найден"),
                ],
            ),
        ),
    ]
