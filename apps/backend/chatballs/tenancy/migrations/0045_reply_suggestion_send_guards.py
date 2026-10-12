"""Protect the source/send association and freeze the actual worker history."""

from importlib import import_module

from django.db import migrations

storage = import_module("chatballs.tenancy.migrations.0041_reply_assistance_guards")
TABLE = "ai_replysuggestionsend"
RELATIONS = (("ai_replysuggestion", "suggestion_id"),
             ("conversations_message", "message_id"),
             ("identity_employeeprofile", "sent_by_id"))


def apply_guards(apps, schema_editor):
    source = storage.IMMUTABILITY.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
    source = source.replace("'history_version', 'created_at'", "'created_at'")
    source = source.replace("    RETURN NEW;", """
    IF NEW.history_version IS DISTINCT FROM OLD.history_version AND NOT
        (OLD.status = 'PENDING' AND NEW.status = 'RUNNING') THEN
        RAISE EXCEPTION 'immutable reply assistance history';
    END IF;
    RETURN NEW;""")
    schema_editor.execute(source)
    schema_editor.execute(storage.RLS.format(table=TABLE))
    for parent, column in RELATIONS:
        schema_editor.execute(
            f"CREATE CONSTRAINT TRIGGER {TABLE}_{column}_tenant "
            f"AFTER INSERT OR UPDATE ON {TABLE} DEFERRABLE INITIALLY IMMEDIATE "
            f"FOR EACH ROW EXECUTE FUNCTION chatballs.enforce_tenant_fk('{parent}', '{column}')"
        )
    schema_editor.execute("""
CREATE FUNCTION chatballs.protect_reply_suggestion_send() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        RAISE EXCEPTION 'immutable reply suggestion send';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM ai_replysuggestion s
        JOIN ai_replyassistanceattempt a ON a.id = s.attempt_id
        JOIN conversations_message m ON m.id = NEW.message_id
        JOIN identity_employeeprofile e ON e.id = NEW.sent_by_id
        WHERE s.id = NEW.suggestion_id AND s.status = 'READY' AND s.rejected_at IS NULL
          AND a.conversation_id = m.conversation_id
          AND m.author_type = 'OPERATOR' AND m.author_user_id = e.user_id
          AND s.organization_id = NEW.organization_id
          AND m.organization_id = NEW.organization_id AND e.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'invalid reply suggestion send association';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER ai_replysuggestionsend_source BEFORE INSERT OR UPDATE ON ai_replysuggestionsend
FOR EACH ROW EXECUTE FUNCTION chatballs.protect_reply_suggestion_send();
""")


def remove_guards(apps, schema_editor):
    schema_editor.execute(f"DROP TRIGGER IF EXISTS {TABLE}_source ON {TABLE}")
    schema_editor.execute("DROP FUNCTION IF EXISTS chatballs.protect_reply_suggestion_send()")
    for _, column in RELATIONS:
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {TABLE}_{column}_tenant ON {TABLE}")
    for policy in ("chatballs_tenant_isolation", "chatballs_schema_access"):
        schema_editor.execute(f"DROP POLICY IF EXISTS {policy} ON {TABLE}")
    schema_editor.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
    schema_editor.execute(storage.IMMUTABILITY.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_assistance_history"),
        ("ai", "0026_reply_suggestion_send"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
