from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("conversations", "0048_merge_native_mirror_and_v119_reply_snapshot")]

    operations = [
        migrations.AlterField(
            model_name="conversationevent",
            name="transport",
            field=models.CharField(
                max_length=8,
                choices=[
                    ("MAX", "Max"),
                    ("TELEGRAM", "Telegram"),
                    ("VK", "Vk"),
                    ("WEB", "Web"),
                    ("EMAIL", "Email"),
                    ("GATEWAY", "Gateway"),
                ],
                null=True,
                blank=True,
            ),
        ),
        migrations.RemoveConstraint(
            model_name="conversationevent",
            name="domain_event_transport_valid",
        ),
        migrations.AddConstraint(
            model_name="conversationevent",
            constraint=models.CheckConstraint(
                condition=models.Q(transport__isnull=True)
                | models.Q(transport__in=["MAX", "TELEGRAM", "VK", "WEB", "EMAIL", "GATEWAY"]),
                name="domain_event_transport_valid",
            ),
        ),
    ]
