"""Participation is tenant-owned, including every membership reference."""

from django.db import migrations

TABLE = "conversations_conversationparticipant"
RELATIONS = (
    ("conversations_conversation", "conversation_id"),
    ("identity_employeeprofile", "membership_id"),
    ("identity_employeeprofile", "joined_by_id"),
    ("identity_employeeprofile", "left_by_id"),
)

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
    schema_editor.execute(RLS.format(table=TABLE))
    for parent, column in RELATIONS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER participant_{column}_tenant
            AFTER INSERT OR UPDATE ON {TABLE}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)


def remove_guards(apps, schema_editor):
    for _, column in RELATIONS:
        schema_editor.execute(f"DROP TRIGGER participant_{column}_tenant ON {TABLE}")
    schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {TABLE}")
    schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {TABLE}")
    schema_editor.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app")
    schema_editor.execute(
        f"REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app"
    )


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0041_transfer_guards"),
        ("conversations", "0031_participant_data"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
