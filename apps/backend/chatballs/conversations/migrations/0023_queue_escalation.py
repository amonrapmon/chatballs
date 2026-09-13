"""Личная очередь и пороги эскалации.

assigned_at нужен, чтобы у назначения был срок: waiting_since для этого не
годится — назначить могут и через час после того, как диалог встал в очередь.
Пороги — строка на организацию с дефолтами: «долго» у круглосуточной
поддержки и у приёма по будням означает разное.
"""


import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0022_conversation_waiting_since'),
        ('identity', '0039_remove_organization_currency'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='assigned_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='message',
            name='system_event',
            field=models.CharField(blank=True, choices=[('operator_took', 'Оператор перехватил диалог'), ('returned_to_ai', 'Диалог возвращён AI'), ('returned_to_queue', 'Диалог возвращён в очередь'), ('ai_unavailable', 'AI недоступен'), ('ai_handed_over', 'AI передал диалог оператору'), ('assigned_to', 'Диалог назначен сотруднику'), ('assignment_expired', 'Назначение истекло'), ('call_requested', 'Запрошен звонок'), ('call_accepted', 'Клиент принял приглашение'), ('call_declined', 'Клиент отклонил приглашение'), ('call_cancelled', 'Приглашение отменено'), ('call_missed', 'Звонок пропущен'), ('call_expired', 'Приглашение истекло'), ('call_started', 'Звонок начался'), ('call_ended', 'Звонок завершён'), ('call_failed', 'Звонок не состоялся')], default='', max_length=32),
        ),
        migrations.CreateModel(
            name='QueueEscalationPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('remind_after_minutes', models.PositiveIntegerField(default=5)),
                ('widen_after_minutes', models.PositiveIntegerField(default=15)),
                ('escalate_after_minutes', models.PositiveIntegerField(default=30)),
                ('assignment_timeout_minutes', models.PositiveIntegerField(default=10)),
                ('organization', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='queue_policy', to='identity.organization')),
            ],
            options={
                'db_table': 'conversations_queueescalationpolicy',
            },
        ),
    ]
