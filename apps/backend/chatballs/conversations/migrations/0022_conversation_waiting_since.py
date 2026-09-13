"""Время ожидания в очереди — отдельным полем.

Раньше «дольше всех ждущий» вычислялся по времени последнего сообщения, и
очередь работала обратно смыслу: клиент, напомнивший о себе, двигал
last_message_at вперёд и падал в конец очереди. Поле ставится один раз при входе
в очередь (chatballs.conversations.queue) и снимается при выходе из неё.

Backfill берёт last_message_at — единственное, что известно про уже ждущие
диалоги. Для них порядок не ухудшится: в старой сортировке ключ был тот же.
"""

from django.db import migrations, models

BACKFILL = """
UPDATE conversations_conversation
SET waiting_since = last_message_at
WHERE lifecycle = 'OPEN' AND control_mode = 'PAUSED' AND waiting_since IS NULL
"""


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0021_i18n_events'),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='waiting_since',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunSQL(sql=BACKFILL, reverse_sql=migrations.RunSQL.noop),
        migrations.AddIndex(
            model_name='conversation',
            index=models.Index(
                fields=['organization', 'waiting_since'], name='conv_waiting_order'
            ),
        ),
    ]
