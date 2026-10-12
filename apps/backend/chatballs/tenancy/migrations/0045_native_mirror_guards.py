"""RLS, runtime grants and tenant FK constraints for Native Mirror.

Both tables belong to the caller organization, not to the platform role.
The app role can see them only inside tenant_atomic(); schema role migrates.
"""

from django.db import migrations


TABLES = (
    "native_mirror_nativemirrorconversationstate",
    "native_mirror_nativemirrorreceipt",
)

FOREIGN_KEYS = {
    TABLES[0]: (
        ("conversations_conversation", "conversation_id"),
    ),
    TABLES[1]: (
        ("integrations_integration", "integration_id"),
        ("conversations_conversation", "conversation_id"),
        ("conversations_message", "message_id"),
    ),
}

POLICIES = """
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
        schema_editor.execute(POLICIES.format(table=table))
        for parent, column in FOREIGN_KEYS[table]:
            schema_editor.execute(
                f"CREATE CONSTRAINT TRIGGER {table}_{column}_tenant "
                f"AFTER INSERT OR UPDATE ON {table} "
                "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION "
                f"chatballs.enforce_tenant_fk('{parent}', '{column}')"
            )
    table = TABLES[1]
    schema_editor.execute(
        f"CREATE CONSTRAINT TRIGGER native_mirror_receipt_author_tenant "
        f"AFTER INSERT OR UPDATE ON {table} "
        "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION "
        "chatballs.enforce_tenant_user('author_user_id')"
    )


def remove_guards(apps, schema_editor):
    schema_editor.execute(
        f"DROP TRIGGER IF EXISTS native_mirror_receipt_author_tenant ON {TABLES[1]}"
    )
    for table in reversed(TABLES):
        for _parent, column in FOREIGN_KEYS[table]:
            schema_editor.execute(f"DROP TRIGGER IF EXISTS {table}_{column}_tenant ON {table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
        schema_editor.execute(
            f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app"
        )


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0044_merge_gateway_and_turn_diagnostic_guards"),
        ("native_mirror", "0001_initial"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
