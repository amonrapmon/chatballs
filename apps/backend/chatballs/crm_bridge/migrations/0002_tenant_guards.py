"""RLS and PostgreSQL tenant FK guards, kept inside crm_bridge migrations."""

from django.db import migrations


TABLES = (
    "crm_bridge_crmorganizationconfig",
    "crm_bridge_crmcompany",
    "crm_bridge_crmconnectionbinding",
)

FK_GUARDS = {
    "crm_bridge_crmconnectionbinding": (
        ("integrations_integration", "integration_id"),
        ("crm_bridge_crmcompany", "crm_company_id"),
    ),
}

RLS_SQL = """
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
        schema_editor.execute(RLS_SQL.format(table=table))
        for referenced_table, column in FK_GUARDS.get(table, ()):
            schema_editor.execute(
                f"CREATE CONSTRAINT TRIGGER {table}_{column}_tenant "
                f"AFTER INSERT OR UPDATE ON {table} "
                "DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION "
                f"chatballs.enforce_tenant_fk('{referenced_table}', '{column}')"
            )


def remove_guards(apps, schema_editor):
    for table in reversed(TABLES):
        for _referenced_table, column in FK_GUARDS.get(table, ()):
            schema_editor.execute(
                f"DROP TRIGGER IF EXISTS {table}_{column}_tenant ON {table}"
            )
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
        ("crm_bridge", "0001_initial"),
        ("tenancy", "0046_native_mirror_publication_guards"),
    ]

    operations = [migrations.RunPython(apply_guards, remove_guards)]
