from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0033_message_delivery_suppressed"),
        ("conversations", "0047_message_reply_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="message",
            name="delivery_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Не задано"),
                    ("queued", "В очереди"),
                    ("suppressed", "Отменено до отправки"),
                    ("provider_accepted", "Принято провайдером"),
                    ("delivered", "Доставлено"),
                    ("read", "Прочитано"),
                    ("failed", "Ошибка доставки"),
                    ("no_account", "Аккаунт не найден"),
                ],
                default="",
                max_length=32,
            ),
        ),
    ]
