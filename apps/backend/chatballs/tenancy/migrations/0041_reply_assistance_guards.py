"""Tenant-защита и неизменность источника предложений (SPEC-0024)."""

from django.db import migrations

TABLES = {
    "ai_replyassistanceattempt": (
        ("conversations_conversation", "conversation_id"),
        ("ai_aiagent", "agent_id"),
        ("identity_employeeprofile", "requested_by_id"),
    ),
    "ai_replysuggestion": (
        ("ai_replyassistanceattempt", "attempt_id"),
        ("identity_employeeprofile", "requested_by_id"),
        ("identity_employeeprofile", "rejected_by_id"),
    ),
}

RLS = """
ALTER TABLE {table} OWNER TO chatballs_schema;
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {table} FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO chatballs_runtime_app;
GRANT ALL ON TABLE {table} TO chatballs_schema;
GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO chatballs_runtime_app, chatballs_schema;
CREATE POLICY chatballs_tenant_isolation ON {table}
    FOR ALL TO chatballs_runtime_app
    USING (organization_id = chatballs.current_organization_id())
    WITH CHECK (organization_id = chatballs.current_organization_id());
CREATE POLICY chatballs_schema_access ON {table}
    FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);
"""

IMMUTABILITY = """
CREATE FUNCTION chatballs.protect_reply_assistance_source() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE column_name text;
BEGIN
    FOREACH column_name IN ARRAY ARRAY[
        'organization_id', 'public_id', 'operation_key', 'requested_by_id',
        'history_version', 'created_at'
    ] || TG_ARGV LOOP
        IF (to_jsonb(NEW) -> column_name) IS DISTINCT FROM (to_jsonb(OLD) -> column_name) THEN
            RAISE EXCEPTION 'immutable reply assistance source: %%', column_name;
        END IF;
    END LOOP;
    IF OLD.started_at IS NOT NULL AND NEW.started_at IS DISTINCT FROM OLD.started_at THEN
        RAISE EXCEPTION 'immutable reply assistance start time';
    END IF;
    IF OLD.status IN ('READY', 'ERROR') AND
        ROW(NEW.status, NEW.completed_at, NEW.error_code) IS DISTINCT FROM
        ROW(OLD.status, OLD.completed_at, OLD.error_code) THEN
        RAISE EXCEPTION 'terminal reply assistance operation';
    END IF;
    IF OLD.status = 'RUNNING' AND NEW.status = 'PENDING' THEN
        RAISE EXCEPTION 'reply assistance operation cannot be repeated';
    END IF;
    IF TG_TABLE_NAME = 'ai_replysuggestion' THEN
        IF OLD.status = 'READY' AND NEW.original_text IS DISTINCT FROM OLD.original_text THEN
            RAISE EXCEPTION 'immutable original reply suggestion';
        END IF;
        IF OLD.rejected_at IS NOT NULL AND
            ROW(NEW.rejected_by_id, NEW.rejected_at) IS DISTINCT FROM
            ROW(OLD.rejected_by_id, OLD.rejected_at) THEN
            RAISE EXCEPTION 'immutable reply suggestion rejection';
        END IF;
    END IF;
    RETURN NEW;
END $$;
"""


def apply_guards(apps, schema_editor):
    schema_editor.execute(IMMUTABILITY)
    for table, relations in TABLES.items():
        schema_editor.execute(RLS.format(table=table))
        for parent, column in relations:
            schema_editor.execute(
                f"CREATE CONSTRAINT TRIGGER {table}_{column}_tenant "
                f"AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY IMMEDIATE "
                "FOR EACH ROW EXECUTE FUNCTION "
                f"chatballs.enforce_tenant_fk('{parent}', '{column}')"
            )
        fields = "'conversation_id', 'agent_id'" if table == "ai_replyassistanceattempt" else "'attempt_id', 'position'"
        schema_editor.execute(
            f"CREATE TRIGGER {table}_source BEFORE UPDATE ON {table} "
            f"FOR EACH ROW EXECUTE FUNCTION chatballs.protect_reply_assistance_source({fields})"
        )


def remove_guards(apps, schema_editor):
    for table, relations in TABLES.items():
        schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_source ON {table}")
        for _parent, column in relations:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_{column}_tenant ON {table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
        schema_editor.execute(
            f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app"
        )
    schema_editor.execute("DROP FUNCTION IF EXISTS chatballs.protect_reply_assistance_source()")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0040_agent_tool_guards"),
        ("ai", "0025_reply_assistance"),
    ]

    operations = [migrations.RunPython(apply_guards, remove_guards)]
