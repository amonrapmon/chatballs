"""Удалять комментарии вместе с диалогом средствами базы.

Runtime-роль может только читать и добавлять комментарии, поэтому каскад Django
при удалении диалога упирался в отказ в доступе. Каскад внешнего ключа выполняет
владелец таблицы: отдельную запись роль по-прежнему удалить не может.
"""

import django.db.models.deletion
from django.db import migrations, models

TABLE = "conversations_conversationcomment"

REPLACE_FK = """
DO $$
DECLARE fk text;
BEGIN
    SELECT conname INTO STRICT fk FROM pg_constraint
    WHERE conrelid = '{table}'::regclass AND contype = 'f'
      AND confrelid = 'conversations_conversation'::regclass;
    EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', fk);
    EXECUTE format(
        'ALTER TABLE {table} ADD CONSTRAINT %I FOREIGN KEY (conversation_id) '
        'REFERENCES conversations_conversation (id) {action}'
        'DEFERRABLE INITIALLY DEFERRED', fk
    );
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [("conversations", "0034_merge_handling_rules_and_comments")]

    operations = [
        migrations.AlterField(
            model_name="conversationcomment",
            name="conversation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="comments",
                to="conversations.conversation",
            ),
        ),
        migrations.RunSQL(
            REPLACE_FK.format(table=TABLE, action="ON DELETE CASCADE "),
            REPLACE_FK.format(table=TABLE, action=""),
        ),
    ]
