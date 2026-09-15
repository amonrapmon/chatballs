"""Агент перестаёт дублировать модель интеграции.

Раньше модель копировалась на агента при каждом сохранении, и поле означало
«то же, что у интеграции». Теперь заполненное поле означает выбор человека:
агент отвечает именно этой моделью, даже если у интеграции другая по
умолчанию. Чтобы смена настройки провайдера не перестала доезжать до агентов,
которым модель никто не выбирал, совпадающее значение очищается — такие агенты
продолжают следовать за интеграцией.
"""

from django.db import migrations


def release_copied_models(apps, schema_editor):
    AIAgent = apps.get_model("ai", "AIAgent")
    updated = []
    for agent in AIAgent.objects.select_related("provider_integration").exclude(model=""):
        integration = agent.provider_integration
        default_model = str((integration.config or {}).get("default_model") or "") if integration else ""
        if agent.model == default_model:
            agent.model = ""
            updated.append(agent)
    AIAgent.objects.bulk_update(updated, ["model"])


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0021_aiagent_transcription_model_alter_aiagent_model"),
    ]

    operations = [
        migrations.RunPython(release_copied_models, migrations.RunPython.noop),
    ]
