"""Правила обработки обращений и журнал их исполнений.

Возврат непринятого назначения работал и раньше, поэтому каждой организации
заводится его правило — включённое и с тем сроком, который у неё уже настроен
в порогах очереди. Остальные правила строк не получают и остаются выключенными:
новых сообщений клиенту миграция не включает. Журнал начинается пустым.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

PRESERVE_ASSIGNMENT_RETURN = """
INSERT INTO conversations_handlingrule
    (organization_id, kind, enabled, version, delay_minutes, conditions, recipients)
SELECT organization.id, 'ASSIGNMENT_RETURN', true, 1,
       COALESCE(policy.assignment_timeout_minutes, 10),
       '{}'::jsonb, '["CONVERSATION_GROUP"]'::jsonb
FROM identity_organization AS organization
LEFT JOIN conversations_queueescalationpolicy AS policy
       ON policy.organization_id = organization.id
"""


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0032_domain_event_data'),
        ('identity', '0042_organization_participant_limit'),
        ('notifications', '0014_new_dialog_type'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='HandlingRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('kind', models.CharField(choices=[('RECEIPT_CONFIRMATION', 'Receipt Confirmation'), ('WAIT_EXCEEDED_NOTICE', 'Wait Exceeded Notice'), ('REPLY_REMINDER', 'Reply Reminder'), ('ASSIGNMENT_RETURN', 'Assignment Return')], max_length=24)),
                ('enabled', models.BooleanField(default=False)),
                ('version', models.PositiveIntegerField(default=1)),
                ('delay_minutes', models.PositiveIntegerField(blank=True, null=True)),
                ('conditions', models.JSONField(blank=True, default=dict)),
                ('recipients', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(blank=True, null=True)),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='handling_rules', to='identity.organization')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.CreateModel(
            name='RuleExecution',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rule_version', models.PositiveIntegerField()),
                ('action', models.CharField(choices=[('RETURN_TO_QUEUE', 'Return To Queue')], max_length=24)),
                ('scheduled_for', models.DateTimeField()),
                ('finished_at', models.DateTimeField(blank=True, null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('EXECUTED', 'Executed'), ('SKIPPED', 'Skipped'), ('FAILED', 'Failed')], default='PENDING', max_length=8)),
                ('reason', models.CharField(blank=True, max_length=32)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('conversation', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rule_executions', to='conversations.conversation')),
                ('message', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='conversations.message')),
                ('notification', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='notifications.notification')),
                ('organization', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='+', to='identity.organization')),
                ('rule', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='executions', to='conversations.handlingrule')),
                ('source_event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rule_executions', to='conversations.conversationevent')),
            ],
            options={
                'ordering': ['-scheduled_for', '-id'],
            },
        ),
        migrations.AddConstraint(
            model_name='handlingrule',
            constraint=models.UniqueConstraint(fields=('organization', 'kind'), name='uniq_handling_rule_org_kind'),
        ),
        migrations.AddConstraint(
            model_name='handlingrule',
            constraint=models.CheckConstraint(condition=models.Q(('kind__in', ['RECEIPT_CONFIRMATION', 'WAIT_EXCEEDED_NOTICE', 'REPLY_REMINDER', 'ASSIGNMENT_RETURN'])), name='handling_rule_kind_valid'),
        ),
        migrations.AddConstraint(
            model_name='handlingrule',
            constraint=models.CheckConstraint(condition=models.Q(('version__gt', 0)), name='handling_rule_version_positive'),
        ),
        migrations.AddConstraint(
            model_name='handlingrule',
            constraint=models.CheckConstraint(condition=models.Q(('delay_minutes__isnull', True), models.Q(('delay_minutes__gte', 1), ('delay_minutes__lte', 1440)), _connector='OR'), name='handling_rule_delay_range'),
        ),
        migrations.AddConstraint(
            model_name='handlingrule',
            constraint=models.CheckConstraint(condition=models.Q(('enabled', False), ('delay_minutes__isnull', False), _connector='OR'), name='handling_rule_enabled_has_delay'),
        ),
        migrations.AddIndex(
            model_name='ruleexecution',
            index=models.Index(fields=['organization', 'scheduled_for'], name='rule_execution_period_idx'),
        ),
        migrations.AddIndex(
            model_name='ruleexecution',
            index=models.Index(fields=['conversation', 'status'], name='rule_execution_pending_idx'),
        ),
        migrations.AddConstraint(
            model_name='ruleexecution',
            constraint=models.UniqueConstraint(fields=('organization', 'rule', 'source_event', 'action'), name='uniq_rule_execution_logical_key'),
        ),
        migrations.AddConstraint(
            model_name='ruleexecution',
            constraint=models.CheckConstraint(condition=models.Q(('action__in', ['RETURN_TO_QUEUE'])), name='rule_execution_action_valid'),
        ),
        migrations.AddConstraint(
            model_name='ruleexecution',
            constraint=models.CheckConstraint(condition=models.Q(('status__in', ['PENDING', 'EXECUTED', 'SKIPPED', 'FAILED'])), name='rule_execution_status_valid'),
        ),
        migrations.AddConstraint(
            model_name='ruleexecution',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('finished_at__isnull', True), ('status', 'PENDING')), models.Q(models.Q(('status', 'PENDING'), _negated=True), ('finished_at__isnull', False)), _connector='OR'), name='rule_execution_finished_matches_status'),
        ),
        migrations.AddConstraint(
            model_name='ruleexecution',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('status__in', ['SKIPPED', 'FAILED']), models.Q(('reason', ''), _negated=True)), models.Q(('reason', ''), ('status__in', ['PENDING', 'EXECUTED'])), _connector='OR'), name='rule_execution_reason_matches_status'),
        ),
        migrations.RunSQL(PRESERVE_ASSIGNMENT_RETURN, migrations.RunSQL.noop),
    ]
