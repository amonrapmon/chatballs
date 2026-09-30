from django.db import migrations


TABLE = "contact_field_values"

FORWARD_SQL = f"""
ALTER TABLE {TABLE} OWNER TO chatballs_schema;
ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {TABLE} TO chatballs_runtime_app;
GRANT ALL ON TABLE {TABLE} TO chatballs_schema;
GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO chatballs_runtime_app, chatballs_schema;
DROP POLICY IF EXISTS chatballs_tenant_isolation ON {TABLE};
CREATE POLICY chatballs_tenant_isolation ON {TABLE}
    FOR ALL TO chatballs_runtime_app
    USING (organization_id = chatballs.current_organization_id())
    WITH CHECK (organization_id = chatballs.current_organization_id());
DROP POLICY IF EXISTS chatballs_schema_access ON {TABLE};
CREATE POLICY chatballs_schema_access ON {TABLE}
    FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);

CREATE CONSTRAINT TRIGGER contact_field_value_contact
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
chatballs.enforce_tenant_fk('conversations_contact', 'contact_id');
CREATE CONSTRAINT TRIGGER contact_field_value_integration
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
chatballs.enforce_tenant_fk('integrations_integration', 'integration_id');
"""

REVERSE_SQL = f"""
DROP TRIGGER IF EXISTS contact_field_value_integration ON {TABLE};
DROP TRIGGER IF EXISTS contact_field_value_contact ON {TABLE};
DROP POLICY IF EXISTS chatballs_tenant_isolation ON {TABLE};
DROP POLICY IF EXISTS chatballs_schema_access ON {TABLE};
ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0038_widget_asset_guards"),
        ("conversations", "0027_contact_email_contactfieldvalue"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
