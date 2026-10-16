"""Tenant-checked immutable snapshots and database-assigned fact ordering."""

from django.db import migrations

TABLE = "conversations_conversationevent"
BOUNDARY = "conversations_conversationeventhistorystart"
RELATIONS = (
    ("conversations_conversation", "conversation_id"),
    ("identity_employeegroup", "group_id"),
    ("integrations_integration", "connection_id"),
)
USERS = ("initiated_by_id", "responsible_id")

FACT_INSERT = """
CREATE FUNCTION chatballs.prepare_conversation_fact() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    -- Serialize with domain changes and other inserts in this conversation.
    PERFORM id FROM conversations_conversation
        WHERE id = NEW.conversation_id AND organization_id = NEW.organization_id
        FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'domain event conversation unavailable'; END IF;
    IF NEW.connection_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM integrations_integration
        WHERE id = NEW.connection_id AND organization_id = NEW.organization_id
          AND kind = 'MESSENGER' AND provider = NEW.transport
    ) THEN RAISE EXCEPTION 'domain event transport mismatch'; END IF;
    SELECT COALESCE(MAX(sequence), 0) + 1 INTO NEW.sequence
        FROM conversations_conversationevent
        WHERE conversation_id = NEW.conversation_id;
    NEW.occurred_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER domain_event_prepare BEFORE INSERT ON conversations_conversationevent
    FOR EACH ROW EXECUTE FUNCTION chatballs.prepare_conversation_fact();
CREATE FUNCTION chatballs.reject_conversation_fact_update() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'domain events are immutable';
END $$;
CREATE TRIGGER domain_event_immutable BEFORE UPDATE ON conversations_conversationevent
    FOR EACH ROW EXECUTE FUNCTION chatballs.reject_conversation_fact_update();
"""


def apply_guards(apps, schema_editor):
    for table in (TABLE, BOUNDARY):
        schema_editor.execute(f"""
            ALTER TABLE {table} OWNER TO chatballs_schema;
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            REVOKE ALL ON TABLE {table} FROM PUBLIC;
            GRANT ALL ON TABLE {table} TO chatballs_schema;
            CREATE POLICY chatballs_schema_access ON {table}
                FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);
        """)
    schema_editor.execute(f"""
        GRANT SELECT, INSERT, DELETE ON TABLE {TABLE} TO chatballs_runtime_app;
        GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq TO chatballs_runtime_app, chatballs_schema;
        CREATE POLICY chatballs_tenant_isolation ON {TABLE}
            FOR ALL TO chatballs_runtime_app
            USING (organization_id = chatballs.current_organization_id())
            WITH CHECK (organization_id = chatballs.current_organization_id());
        -- This single non-tenant timestamp contains no organization data.
        GRANT SELECT ON TABLE {BOUNDARY} TO chatballs_runtime_app;
        CREATE POLICY chatballs_history_read ON {BOUNDARY}
            FOR SELECT TO chatballs_runtime_app USING (true);
    """)
    for parent, column in RELATIONS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER domain_event_{column}_tenant
            AFTER INSERT ON {TABLE}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)
    for column in USERS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER domain_event_{column}_tenant
            AFTER INSERT ON {TABLE}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_user('{column}');
        """)
    schema_editor.execute(FACT_INSERT)


def remove_guards(apps, schema_editor):
    schema_editor.execute(f"DROP TRIGGER domain_event_prepare ON {TABLE}")
    schema_editor.execute(f"DROP TRIGGER domain_event_immutable ON {TABLE}")
    schema_editor.execute("DROP FUNCTION chatballs.prepare_conversation_fact()")
    schema_editor.execute("DROP FUNCTION chatballs.reject_conversation_fact_update()")
    for column in (*[column for _, column in RELATIONS], *USERS):
        schema_editor.execute(f"DROP TRIGGER domain_event_{column}_tenant ON {TABLE}")
    schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {TABLE}")
    schema_editor.execute(f"DROP POLICY chatballs_history_read ON {BOUNDARY}")
    for table in (TABLE, BOUNDARY):
        schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
    schema_editor.execute(f"REVOKE ALL ON SEQUENCE {TABLE}_id_seq FROM chatballs_runtime_app")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0042_participant_guards"),
        ("conversations", "0032_domain_event_data"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
