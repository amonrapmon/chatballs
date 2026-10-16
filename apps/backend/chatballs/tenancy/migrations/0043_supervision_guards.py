"""Tenant isolation and relation checks for supervisor control groups."""

from django.db import migrations

TABLE = "identity_employeegroupsupervision"
RELATIONS = (
    ("identity_employeegroup", "group_id"),
    ("identity_employeeprofile", "employee_id"),
)


def apply_guards(apps, schema_editor):
    schema_editor.execute(f"""
        ALTER TABLE {TABLE} OWNER TO chatballs_schema;
        ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
        REVOKE ALL ON TABLE {TABLE} FROM PUBLIC;
        GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {TABLE} TO chatballs_runtime_app;
        GRANT ALL ON TABLE {TABLE} TO chatballs_schema;
        GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO chatballs_runtime_app, chatballs_schema;
        CREATE POLICY chatballs_tenant_isolation ON {TABLE}
            FOR ALL TO chatballs_runtime_app
            USING (organization_id = chatballs.current_organization_id())
            WITH CHECK (organization_id = chatballs.current_organization_id());
        CREATE POLICY chatballs_schema_access ON {TABLE}
            FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);
    """)
    for parent, column in RELATIONS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER supervision_{column}_tenant
            AFTER INSERT OR UPDATE ON {TABLE}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)


def remove_guards(apps, schema_editor):
    for _, column in RELATIONS:
        schema_editor.execute(f"DROP TRIGGER supervision_{column}_tenant ON {TABLE}")
    schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {TABLE}")
    schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {TABLE}")
    schema_editor.execute(f"ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY")
    schema_editor.execute(f"ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY")
    schema_editor.execute(f"REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app")
    schema_editor.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0042_participant_guards"),
        ("identity", "0043_supervisor"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
