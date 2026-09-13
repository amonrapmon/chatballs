"""Граница видимости уведомления — та же, что у диалога.

Раньше уведомления фильтровались только правом «видеть диалоги», а сами диалоги
— ещё и группой (ADR-CHATBALLS-0043 §4). Из-за расхождения оператор одной группы
получал оклик с именем клиента и куском переписки по диалогу другой группы и,
перейдя по нему, упирался в «диалог не найден».

Старые записи остаются с NULL: группу диалога, из которого они родились, задним
числом восстанавливать нечем, а NULL здесь означает прежнее поведение — видно
всем, кого пропускает аудитория.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('identity', '0020_employeegroup_employeegroupmember_and_more'),
        ('notifications', '0010_i18n_events'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='audience_group',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='notifications',
                to='identity.employeegroup',
            ),
        ),
    ]
