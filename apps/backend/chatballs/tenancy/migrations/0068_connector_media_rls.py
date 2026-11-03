"""Runtime RLS and tenant FK guards for staged Connector media identity.

Migration 0053 adds a model. Without explicit grants the runtime app role
cannot SELECT ... FOR UPDATE its rows, even though schema-owner tests pass.
"""
from django.db import migrations

TABLE = "conversations_connectormediaingest"

FORWARD_SQL = f"""
ALTER TABLE {TABLE} OWNER TO chatballs_schema;
ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM PUBLIC;
REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
-- SELECT FOR UPDATE needs UPDATE privilege; a separate BEFORE UPDATE
-- trigger keeps the provider identity immutable at the database boundary.
GRANT SELECT, INSERT, UPDATE ON TABLE {TABLE} TO chatballs_runtime_app;
GRANT ALL ON TABLE {TABLE} TO chatballs_schema;
GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq
    TO chatballs_runtime_app, chatballs_schema;

CREATE POLICY chatballs_tenant_isolation ON {TABLE}
    FOR ALL TO chatballs_runtime_app
    USING (organization_id = chatballs.current_organization_id())
    WITH CHECK (organization_id = chatballs.current_organization_id());
CREATE POLICY chatballs_schema_access ON {TABLE}
    FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);

CREATE CONSTRAINT TRIGGER connector_media_integration_tenant
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW
EXECUTE FUNCTION chatballs.enforce_tenant_fk('integrations_integration', 'integration_id');

CREATE CONSTRAINT TRIGGER connector_media_message_tenant
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW
EXECUTE FUNCTION chatballs.enforce_tenant_fk('conversations_message', 'message_id');

CREATE FUNCTION chatballs.reject_connector_media_identity_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'connector media identity is immutable';
END $$;
ALTER FUNCTION chatballs.reject_connector_media_identity_update() OWNER TO chatballs_schema;
REVOKE ALL ON FUNCTION chatballs.reject_connector_media_identity_update() FROM PUBLIC;
CREATE TRIGGER connector_media_identity_immutable
BEFORE UPDATE ON {TABLE} FOR EACH ROW
EXECUTE FUNCTION chatballs.reject_connector_media_identity_update();
"""

REVERSE_SQL = f"""
DROP TRIGGER connector_media_identity_immutable ON {TABLE};
DROP FUNCTION chatballs.reject_connector_media_identity_update();
DROP TRIGGER connector_media_message_tenant ON {TABLE};
DROP TRIGGER connector_media_integration_tenant ON {TABLE};
DROP POLICY chatballs_tenant_isolation ON {TABLE};
DROP POLICY chatballs_schema_access ON {TABLE};
ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0067_skill_library_guards"),
        ("conversations", "0053_connector_media_lifecycle"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
