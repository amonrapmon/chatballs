"""RLS, tenant FKs and immutable mail routing snapshots (ADR-0035)."""

from django.db import migrations

RELATIONS = {
    "conversations_emailthread": (
        ("conversations_conversation", "conversation_id"),
        ("integrations_integration", "connection_id"),
    ),
    "conversations_emailthreadmessage": (
        ("conversations_emailthread", "thread_id"),
        ("integrations_integration", "connection_id"),
        ("conversations_message", "message_id"),
    ),
    "conversations_emailsendoperation": (
        ("conversations_emailthreadmessage", "letter_id"),
        ("identity_employeeprofile", "initiated_by_id"),
    ),
    "conversations_emailsendattempt": (
        ("conversations_emailsendoperation", "operation_id"),
        ("identity_employeeprofile", "initiated_by_id"),
        ("events_outboxevent", "outbox_event_id"),
    ),
}

RLS = """
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

INTEGRITY = """
CREATE FUNCTION chatballs.enforce_email_continuation() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE parent_record record; source_record record;
BEGIN
    IF TG_OP = 'UPDATE' AND EXISTS (
        SELECT 1 FROM unnest(string_to_array(TG_ARGV[0], ',')) AS keys(key)
        WHERE (to_jsonb(NEW) -> key) IS DISTINCT FROM (to_jsonb(OLD) -> key)
    ) THEN
        RAISE EXCEPTION 'email routing snapshot is immutable';
    END IF;
    CASE TG_TABLE_NAME
    WHEN 'conversations_emailthread' THEN
        SELECT * INTO parent_record FROM integrations_integration WHERE id = NEW.connection_id;
        IF parent_record.provider IS DISTINCT FROM 'EMAIL'
           OR parent_record.kind IS DISTINCT FROM 'MESSENGER' THEN
            RAISE EXCEPTION 'email thread requires EMAIL connection';
        END IF;
        IF TG_OP = 'INSERT' THEN
            IF NOT parent_record.is_active THEN
                RAISE EXCEPTION 'email thread requires active connection';
            END IF;
            SELECT c.contact_id, i.provider INTO source_record
                FROM conversations_conversation c LEFT JOIN integrations_integration i ON i.id = c.connection_id
                WHERE c.id = NEW.conversation_id;
            IF source_record.provider IS DISTINCT FROM 'WEB' THEN
                RAISE EXCEPTION 'email thread requires WEB source';
            END IF;
            IF NEW.recipient <> lower(btrim(NEW.recipient)) OR NOT (
                EXISTS (SELECT 1 FROM conversations_contact
                    WHERE id = source_record.contact_id AND lower(btrim(email)) = NEW.recipient)
                OR EXISTS (SELECT 1 FROM conversations_connectionidentity ci
                    JOIN integrations_integration i ON i.id = ci.connection_id
                    WHERE ci.contact_id = source_record.contact_id AND ci.organization_id = NEW.organization_id
                        AND i.provider = 'EMAIL' AND lower(ci.external_user_id) = NEW.recipient)
            ) THEN
                RAISE EXCEPTION 'email recipient must be saved on the source contact';
            END IF;
        END IF;
    WHEN 'conversations_emailthreadmessage' THEN
        SELECT * INTO parent_record FROM conversations_emailthread WHERE id = NEW.thread_id;
        SELECT conversation_id INTO source_record FROM conversations_message WHERE id = NEW.message_id;
        IF NEW.connection_id IS DISTINCT FROM parent_record.connection_id
           OR source_record.conversation_id IS DISTINCT FROM parent_record.conversation_id THEN
            RAISE EXCEPTION 'email message transport does not match thread';
        END IF;
    WHEN 'conversations_emailsendoperation' THEN
        SELECT direction INTO parent_record FROM conversations_emailthreadmessage WHERE id = NEW.letter_id;
        IF parent_record.direction IS DISTINCT FROM 'OUTBOUND' THEN
            RAISE EXCEPTION 'email operation requires outbound letter';
        END IF;
    WHEN 'conversations_emailsendattempt' THEN
        SELECT ownership INTO parent_record FROM events_outboxevent WHERE id = NEW.outbox_event_id;
        IF parent_record.ownership IS DISTINCT FROM 'TENANT' THEN
            RAISE EXCEPTION 'email attempt requires tenant outbox';
        END IF;
    END CASE;
    RETURN NEW;
END $$;
ALTER FUNCTION chatballs.enforce_email_continuation() OWNER TO chatballs_schema;
REVOKE ALL ON FUNCTION chatballs.enforce_email_continuation() FROM PUBLIC;
"""

SNAPSHOTS = {
    "conversations_emailthread": "organization_id,conversation_id,connection_id,recipient",
    "conversations_emailthreadmessage": "organization_id,thread_id,connection_id,message_id,mail_message_id,direction",
    "conversations_emailsendoperation": "organization_id,letter_id,initiated_by_id,client_key",
    "conversations_emailsendattempt": "organization_id,operation_id,number,initiated_by_id,outbox_event_id,created_at",
}


def apply_guards(apps, schema_editor):
    schema_editor.execute(INTEGRITY)
    for table, relations in RELATIONS.items():
        schema_editor.execute(RLS.format(table=table))
        for parent, column in relations:
            schema_editor.execute(f"""
                CREATE CONSTRAINT TRIGGER email_{column}_tenant
                AFTER INSERT OR UPDATE ON {table}
                DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
                chatballs.enforce_tenant_fk('{parent}', '{column}');
            """)
        schema_editor.execute(f"""
            CREATE TRIGGER zz_email_integrity AFTER INSERT OR UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION chatballs.enforce_email_continuation('{SNAPSHOTS[table]}');
        """)


def remove_guards(apps, schema_editor):
    for table, relations in RELATIONS.items():
        schema_editor.execute(f"DROP TRIGGER zz_email_integrity ON {table}")
        for _, column in relations:
            schema_editor.execute(f"DROP TRIGGER email_{column}_tenant ON {table}")
        schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
        schema_editor.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app")
    schema_editor.execute("DROP FUNCTION chatballs.enforce_email_continuation()")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0042_participant_guards"),
        ("conversations", "0032_email_continuation_data"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
