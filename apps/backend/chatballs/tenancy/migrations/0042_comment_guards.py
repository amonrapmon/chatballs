"""Internal history has its own RLS, relation guards and append-only app grants."""

from django.db import migrations

TABLE = "conversations_conversationcomment"

FORWARD_SQL = f"""
ALTER TABLE {TABLE} OWNER TO chatballs_schema;
ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM PUBLIC;
REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
GRANT SELECT, INSERT ON TABLE {TABLE} TO chatballs_runtime_app;
GRANT ALL ON TABLE {TABLE} TO chatballs_schema;
GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO chatballs_runtime_app, chatballs_schema;
CREATE POLICY chatballs_tenant_isolation ON {TABLE}
    FOR ALL TO chatballs_runtime_app
    USING (organization_id = chatballs.current_organization_id())
    WITH CHECK (organization_id = chatballs.current_organization_id());
CREATE POLICY chatballs_schema_access ON {TABLE}
    FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);

CREATE CONSTRAINT TRIGGER comment_conversation_tenant
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
chatballs.enforce_tenant_fk('conversations_conversation', 'conversation_id');
CREATE CONSTRAINT TRIGGER comment_author_tenant
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
chatballs.enforce_tenant_user('author_id');
"""

REVERSE_SQL = f"""
DROP TRIGGER comment_author_tenant ON {TABLE};
DROP TRIGGER comment_conversation_tenant ON {TABLE};
DROP POLICY chatballs_tenant_isolation ON {TABLE};
DROP POLICY chatballs_schema_access ON {TABLE};
ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM chatballs_runtime_app;
REVOKE USAGE, SELECT ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0041_transfer_guards"),
        ("conversations", "0031_internal_comments"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
