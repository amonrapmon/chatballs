# Учёт стоимости вызовов удалён вместе с лимитами. Считать было нечем: цена
# бралась из ответа провайдера, а его присылает только OpenRouter; на остальных
# оставалась прайс-таблица из двух моделей и ноль для всех прочих. Ни одна
# цифра расхода в продукте не показывалась.
#
# Статус BLOCKED уходит вместе с лимитами — блокировать вызовы больше нечему.
from django.db import migrations, models


def drop_blocked_rows(apps, schema_editor):
    """Строк со снятым статусом в журнале остаться не должно."""

    apps.get_model("ai", "LlmInvocation").objects.filter(status="BLOCKED").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0018_remove_agent_limits"),
    ]

    operations = [
        migrations.RunPython(drop_blocked_rows, migrations.RunPython.noop),
        migrations.RemoveField(model_name="llminvocation", name="cost_micros"),
        migrations.RemoveField(model_name="llminvocation", name="currency"),
        migrations.AlterField(
            model_name="llminvocation",
            name="status",
            field=models.CharField(
                choices=[("SUCCESS", "Успех"), ("ERROR", "Ошибка")],
                default="SUCCESS",
                max_length=16,
            ),
        ),
    ]
