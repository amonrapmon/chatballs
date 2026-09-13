"""Набор типов событий — из макета «Очередь и уведомления», фрейм Q1.

Раньше «клиент запросил оператора» и «диалог долго ждёт» были одним типом
DIALOG_WAITING, и отписаться от второго, не потеряв первое, было нельзя. Теперь
это разные события, и к ним добавилось «диалог назначили на меня».

Старые записи разделяются по dedup_key — единственному, что о них известно
задним числом: ключи эскалации начинаются с «waiting:», ключи назначения — с
«assign:». Всё остальное, что было DIALOG_WAITING, — это просьба о человеке.

Выбор сотрудника в настройках переносится по тому же соответствию, иначе человек после
обновления молча перестал бы получать то, на что подписан.
"""

from django.db import migrations, models

# Старый код -> новый. RELEASE_PUBLISHED не переносится: он был заделом на
# будущее, никогда не отправлялся и в новом наборе ему места нет.
OLD_TO_NEW = {
    "DIALOG_WAITING": "OPERATOR_REQUESTED",
    "INTEGRATION_ERROR": "AI_STOPPED",
}

SPLIT_BY_DEDUP_PREFIX = (
    ("waiting:", "DIALOG_WAITING_LONG"),
    ("assign:", "DIALOG_ASSIGNED"),
)


def forward(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    for old, new in OLD_TO_NEW.items():
        Notification.objects.filter(type=old).update(type=new)
    for prefix, new in SPLIT_BY_DEDUP_PREFIX:
        Notification.objects.filter(
            type="OPERATOR_REQUESTED", dedup_key__startswith=prefix
        ).update(type=new)
    _remap_preferences(apps, {**OLD_TO_NEW})


def backward(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    reverse = {
        "OPERATOR_REQUESTED": "DIALOG_WAITING",
        "DIALOG_WAITING_LONG": "DIALOG_WAITING",
        "DIALOG_ASSIGNED": "DIALOG_WAITING",
        "AI_STOPPED": "INTEGRATION_ERROR",
    }
    for new, old in reverse.items():
        Notification.objects.filter(type=new).update(type=old)
    _remap_preferences(apps, reverse)


def _remap_preferences(apps, mapping):
    """Подписки сотрудников: коды внутри JSON-списка."""
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    for preference in NotificationPreference.objects.all().iterator():
        types = preference.types or []
        moved = [mapping.get(code, code) for code in types]
        # Дубли возможны, когда два старых кода сходятся в один новый.
        unique = list(dict.fromkeys(moved))
        if unique != types:
            preference.types = unique
            preference.save(update_fields=["types"])


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0012_notification_preference'),
    ]

    operations = [
        migrations.RunPython(forward, backward),
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('OPERATOR_REQUESTED', 'Клиент запросил оператора'),
                    ('DIALOG_NEW_MESSAGE', 'Новое сообщение в моём диалоге'),
                    ('DIALOG_ASSIGNED', 'Диалог назначили на меня'),
                    ('DIALOG_WAITING_LONG', 'Диалог долго ждёт человека'),
                    ('AI_STOPPED', 'AI остановлен ошибкой или лимитом'),
                ],
                max_length=32,
            ),
        ),
    ]
