"""«Новый диалог» — отдельное событие (макет Q1, дополнение владельца).

В присланном наборе такого типа не было, и оклик о новом диалоге попал в
«клиент запросил оператора». Но диалог начинается и на канале с работающим
агентом, где человека никто не звал: называть это просьбой о человеке — врать.

Старые записи узнаются по dedup_key «dialog:» — так помечены именно оклики о
новом диалоге. Разделить их по тому, был ли тогда доступен агент, задним числом
нельзя, поэтому все они становятся «новым диалогом»: это верно для
подавляющего большинства (канал с агентом — обычный случай) и, в отличие от
обратного, ничего не приписывает клиенту.

Подписки: кому приходило «клиент запросил оператора», тому добавляется и «новый
диалог». До этой миграции это было одно событие, и человек не должен молча
перестать получать половину того, на что был подписан.
"""

from django.db import migrations, models


def forward(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    Notification.objects.filter(
        type="OPERATOR_REQUESTED", dedup_key__startswith="dialog:"
    ).update(type="NEW_DIALOG")
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    for preference in NotificationPreference.objects.all().iterator():
        types = preference.types or []
        if "OPERATOR_REQUESTED" in types and "NEW_DIALOG" not in types:
            preference.types = ["NEW_DIALOG", *types]
            preference.save(update_fields=["types"])


def backward(apps, schema_editor):
    Notification = apps.get_model("notifications", "Notification")
    Notification.objects.filter(type="NEW_DIALOG").update(type="OPERATOR_REQUESTED")
    NotificationPreference = apps.get_model("notifications", "NotificationPreference")
    for preference in NotificationPreference.objects.all().iterator():
        types = preference.types or []
        if "NEW_DIALOG" in types:
            kept = [code for code in types if code != "NEW_DIALOG"]
            preference.types = kept if "OPERATOR_REQUESTED" in kept else ["OPERATOR_REQUESTED", *kept]
            preference.save(update_fields=["types"])


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0013_notification_types_from_baseline'),
    ]

    operations = [
        migrations.AlterField(
            model_name='notification',
            name='type',
            field=models.CharField(
                choices=[
                    ('NEW_DIALOG', 'Новый диалог'),
                    ('OPERATOR_REQUESTED', 'Клиент запросил оператора'),
                    ('DIALOG_NEW_MESSAGE', 'Новое сообщение в моём диалоге'),
                    ('DIALOG_ASSIGNED', 'Диалог назначили на меня'),
                    ('DIALOG_WAITING_LONG', 'Диалог долго ждёт человека'),
                    ('AI_STOPPED', 'AI остановлен ошибкой или лимитом'),
                ],
                max_length=32,
            ),
        ),
        migrations.RunPython(forward, backward),
    ]
