from django.db import migrations

TABLE = "conversations_assignmentpolicy"
FORWARD = f"""
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
CREATE FUNCTION chatballs.assignment_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.assigned_operator_id IS DISTINCT FROM OLD.assigned_operator_id THEN
        NEW.assignment_version := OLD.assignment_version + 1;
    ELSE
        NEW.assignment_version := OLD.assignment_version;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER conversation_assignment_version
    BEFORE UPDATE ON conversations_conversation
    FOR EACH ROW EXECUTE FUNCTION chatballs.assignment_version();
"""
BACKWARD = f"""
DROP TRIGGER conversation_assignment_version ON conversations_conversation;
DROP FUNCTION chatballs.assignment_version();
DROP POLICY chatballs_tenant_isolation ON {TABLE};
DROP POLICY chatballs_schema_access ON {TABLE};
ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0045_merge_domain_events_work_status_supervision"),
        ("conversations", "0033_assignment_transfer"),
    ]
    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
