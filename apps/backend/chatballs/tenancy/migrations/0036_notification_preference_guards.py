# Настройки оклика (notifications_notificationpreference): tenant-таблица с
# organization_id, RLS и гранты по образцу tenancy/0022. Настройка принадлежит
# сотруднику в организации, читает и пишет её runtime-роль app.
from django.db import migrations

TABLES = ("notifications_notificationpreference",)

FORWARD_RLS = """
ALTER TABLE {table} OWNER TO chatballs_schema;
ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
REVOKE ALL ON {table} FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO chatballs_runtime_app;
GRANT ALL ON {table} TO chatballs_schema;
GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq
    TO chatballs_runtime_app, chatballs_schema;
DROP POLICY IF EXISTS chatballs_tenant_isolation ON {table};
CREATE POLICY chatballs_tenant_isolation ON {table}
    FOR ALL TO chatballs_runtime_app
    USING (organization_id = chatballs.current_organization_id())
    WITH CHECK (organization_id = chatballs.current_organization_id());
DROP POLICY IF EXISTS chatballs_schema_access ON {table};
CREATE POLICY chatballs_schema_access ON {table}
    FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);
"""


def apply_guards(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(FORWARD_RLS.format(table=table))


def remove_guards(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(f"DROP POLICY IF EXISTS chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY IF EXISTS chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0035_organization_creation_and_invitation_directory"),
        ("notifications", "0012_notification_preference"),
    ]

    operations = [migrations.RunPython(apply_guards, remove_guards)]
