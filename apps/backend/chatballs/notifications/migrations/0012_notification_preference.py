"""Настройка оклика уезжает из привязки к мессенджеру в отдельную сущность.

Пока транспорт был один, список типов на привязке работал. Со вторым (браузер) в
профиле оказались бы два списка галочек про одно и то же, и человек, отключивший
«новое сообщение», продолжал бы получать его с другой стороны.

Порядок операций здесь важен: сначала новая таблица, потом перенос, и только
потом удаление старого поля. Django сгенерировал обратный порядок — в нём
настройки всех, кто подключил бота, молча обнулились бы.
"""

import chatballs.notifications.models
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

MESSENGER = "MESSENGER"


def carry_over_push_types(apps, schema_editor):
    MessengerBinding = apps.get_model("notifications", "MessengerBinding")
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    rows = []
    seen = set()
    for binding in MessengerBinding.objects.all().iterator():
        # Мессенджер у сотрудника один на организацию, но привязок в базе могло
        # остаться несколько: берём первую и не плодим дубли под уникальным ключом.
        key = (binding.organization_id, binding.user_id)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            NotificationPreference(
                organization_id=binding.organization_id,
                user_id=binding.user_id,
                transport=MESSENGER,
                # Привязка существует — значит, согласие получать уже дано.
                enabled=True,
                types=binding.push_types or [],
            )
        )
    NotificationPreference.objects.bulk_create(rows, ignore_conflicts=True)


def restore_push_types(apps, schema_editor):
    MessengerBinding = apps.get_model("notifications", "MessengerBinding")
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    by_user = {
        (preference.organization_id, preference.user_id): preference.types
        for preference in NotificationPreference.objects.filter(transport=MESSENGER)
    }
    for binding in MessengerBinding.objects.all().iterator():
        types = by_user.get((binding.organization_id, binding.user_id))
        if types is not None:
            binding.push_types = types
            binding.save(update_fields=["push_types"])


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0039_remove_organization_currency'),
        ('notifications', '0011_notification_audience_group'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationPreference',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('transport', models.CharField(choices=[('BROWSER', 'Браузер'), ('MESSENGER', 'Мессенджер')], max_length=16)),
                ('enabled', models.BooleanField(default=False)),
                ('types', models.JSONField(blank=True, default=chatballs.notifications.models.default_push_types)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='notification_preferences', to='identity.organization')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='notification_preferences', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('organization', 'user', 'transport'), name='uniq_notification_preference')],
            },
        ),
        migrations.RunPython(carry_over_push_types, restore_push_types),
        migrations.RemoveField(
            model_name='messengerbinding',
            name='push_types',
        ),
    ]
