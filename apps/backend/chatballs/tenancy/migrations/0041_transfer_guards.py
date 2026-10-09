"""Transfer data uses the existing tenant policy and cross-tenant guards."""

from django.db import migrations

TABLES = ("conversations_transferreason", "conversations_conversationtransfer")
JOURNAL = TABLES[1]
RELATIONS = (
    ("conversations_conversation", "conversation_id"),
    ("conversations_transferreason", "reason_id"),
)
USERS = ("previous_operator_id", "new_operator_id", "initiated_by_id")

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


def apply_guards(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(RLS.format(table=table))
    for parent, column in RELATIONS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER transfer_{column}_tenant
            AFTER INSERT OR UPDATE ON {JOURNAL}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)
    for column in USERS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER transfer_{column}_tenant
            AFTER INSERT OR UPDATE ON {JOURNAL}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_user('{column}');
        """)


def remove_guards(apps, schema_editor):
    for column in (*[column for _, column in RELATIONS], *USERS):
        schema_editor.execute(f"DROP TRIGGER transfer_{column}_tenant ON {JOURNAL}")
    for table in TABLES:
        schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
        schema_editor.execute(
            f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0040_agent_tool_guards"),
        ("conversations", "0030_transfer_data"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
