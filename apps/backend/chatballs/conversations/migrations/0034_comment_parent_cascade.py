"""Allow parent deletion while keeping comments append-only for runtime SQL."""

import django.db.models.deletion
from django.db import migrations, models


def set_parent_delete(schema_editor, action):
    table = "conversations_conversationcomment"
    parent = "conversations_conversation"
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, table)
    names = [
        name for name, constraint in constraints.items()
        if constraint["columns"] == ["conversation_id"]
        and constraint["foreign_key"] == (parent, "id")
    ]
    if len(names) != 1:
        raise RuntimeError("Expected one comment conversation foreign key")
    quote = schema_editor.quote_name
    schema_editor.execute(f"ALTER TABLE {quote(table)} DROP CONSTRAINT {quote(names[0])}")
    schema_editor.execute(
        f"ALTER TABLE {quote(table)} ADD CONSTRAINT {quote(names[0])} "
        f"FOREIGN KEY (conversation_id) REFERENCES {quote(parent)} (id) "
        f"ON DELETE {action} DEFERRABLE INITIALLY DEFERRED"
    )


def cascade_parent(apps, schema_editor):
    set_parent_delete(schema_editor, "CASCADE")


def restore_parent(apps, schema_editor):
    set_parent_delete(schema_editor, "NO ACTION")


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0033_merge_comments_domain_events"),
        ("tenancy", "0046_merge_domain_event_guards"),
    ]
    operations = [migrations.SeparateDatabaseAndState(
        database_operations=[migrations.RunPython(cascade_parent, restore_parent)],
        state_operations=[migrations.AlterField(
            model_name="conversationcomment", name="conversation",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name="comments", to="conversations.conversation",
            ),
        )],
    )]
