"""Cascade parent deletion without granting DELETE on append-only comments."""

from django.db import migrations, models

TABLE = "conversations_conversationcomment"
PARENT = "conversations_conversation"


def replace_foreign_key(schema_editor, action):
    with schema_editor.connection.cursor() as cursor:
        constraints = schema_editor.connection.introspection.get_constraints(cursor, TABLE)
    names = [
        name for name, constraint in constraints.items()
        if constraint["foreign_key"] == (PARENT, "id")
        and constraint["columns"] == ["conversation_id"]
    ]
    if len(names) != 1:
        raise RuntimeError("Expected one comment conversation foreign key")
    name = schema_editor.quote_name(names[0])
    schema_editor.execute(f"ALTER TABLE {TABLE} DROP CONSTRAINT {name}")
    schema_editor.execute(
        f"ALTER TABLE {TABLE} ADD CONSTRAINT {name} FOREIGN KEY (conversation_id) "
        f"REFERENCES {PARENT} (id) ON DELETE {action} DEFERRABLE INITIALLY DEFERRED"
    )


def cascade_parent_delete(apps, schema_editor):
    replace_foreign_key(schema_editor, "CASCADE")


def restore_parent_key(apps, schema_editor):
    replace_foreign_key(schema_editor, "NO ACTION")


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0034_merge_comments_and_specialist_notice"),
        ("tenancy", "0045_merge_comments_diagnostics_and_collaboration"),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(cascade_parent_delete, restore_parent_key)],
            state_operations=[migrations.AlterField(
                model_name="conversationcomment",
                name="conversation",
                field=models.ForeignKey(
                    on_delete=models.DO_NOTHING, related_name="comments",
                    to="conversations.conversation",
                ),
            )],
        ),
    ]
