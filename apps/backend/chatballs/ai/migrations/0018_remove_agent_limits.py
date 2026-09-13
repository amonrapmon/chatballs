# Дневной бюджет агента снят вместе с полем `limits`: расход считался по
# прайс-таблице из двух моделей, а для всех остальных оставался нулевым — лимит
# не срабатывал никогда. Единственный оставшийся предохранитель — общий лимит
# установки из переменной окружения (CHATBALLS_AI_GLOBAL_DAILY_COST_LIMIT_MICROS).
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("ai", "0017_agent_answer_language"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="aiagent",
            name="limits",
        ),
    ]
