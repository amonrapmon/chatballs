from django.db import migrations

TABLE = "identity_workstatusoperation"


def apply_guards(apps, schema_editor):
    schema_editor.execute(f"""
        ALTER TABLE {TABLE} OWNER TO chatballs_schema;
        ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
        ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
        REVOKE ALL ON TABLE {TABLE} FROM PUBLIC;
        GRANT SELECT, INSERT ON TABLE {TABLE} TO chatballs_runtime_app;
        GRANT ALL ON TABLE {TABLE} TO chatballs_schema;
        GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO chatballs_runtime_app, chatballs_schema;
        CREATE POLICY chatballs_tenant_isolation ON {TABLE}
            FOR ALL TO chatballs_runtime_app
            USING (organization_id = chatballs.current_organization_id())
            WITH CHECK (organization_id = chatballs.current_organization_id());
        CREATE POLICY chatballs_schema_access ON {TABLE}
            FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);
        CREATE CONSTRAINT TRIGGER work_status_membership_tenant
            AFTER INSERT OR UPDATE ON {TABLE}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('identity_employeeprofile', 'membership_id');
    """)


def remove_guards(apps, schema_editor):
    schema_editor.execute(f"""
        DROP TRIGGER work_status_membership_tenant ON {TABLE};
        DROP POLICY chatballs_tenant_isolation ON {TABLE};
        DROP POLICY chatballs_schema_access ON {TABLE};
        ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;
        ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;
        REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
        REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app;
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0041_transfer_guards"),
        ("identity", "0042_work_status"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
