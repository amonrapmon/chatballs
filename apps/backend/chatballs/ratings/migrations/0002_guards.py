"""Forced RLS, immutable attribution and completion/response consistency."""

from django.db import migrations

TABLES = ("ratings_ratingsettings", "ratings_ratingrequest", "ratings_customerrating")

GUARDS = """
CREATE FUNCTION chatballs.valid_rating_scale(scale jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE AS $$
DECLARE choice jsonb; position integer := 0;
BEGIN
    IF jsonb_typeof(scale) <> 'array' THEN RETURN false; END IF;
    IF jsonb_array_length(scale) <> 5 THEN RETURN false; END IF;
    FOR choice IN SELECT * FROM jsonb_array_elements(scale) LOOP
        position := position + 1;
        IF jsonb_typeof(choice) <> 'object' THEN RETURN false; END IF;
        IF choice->'value' IS DISTINCT FROM to_jsonb(position)
            OR jsonb_typeof(choice->'label') IS DISTINCT FROM 'string'
            OR length(btrim(choice->>'label')) NOT BETWEEN 1 AND 120
        THEN RETURN false; END IF;
    END LOOP;
    RETURN true;
END $$;
CREATE FUNCTION chatballs.guard_rating_request() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE completion conversations_conversationevent%%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - ARRAY['sent_at', 'cancelled_at', 'credential_hash', 'expires_at'])
            IS DISTINCT FROM
           (to_jsonb(OLD) - ARRAY['sent_at', 'cancelled_at', 'credential_hash', 'expires_at'])
        THEN RAISE EXCEPTION 'rating snapshot is immutable'; END IF;
        IF OLD.sent_at IS NOT NULL AND
           ROW(NEW.sent_at, NEW.credential_hash, NEW.expires_at) IS DISTINCT FROM
           ROW(OLD.sent_at, OLD.credential_hash, OLD.expires_at)
        THEN RAISE EXCEPTION 'rating credential is immutable'; END IF;
        IF OLD.cancelled_at IS NOT NULL AND NEW.cancelled_at IS DISTINCT FROM OLD.cancelled_at
        THEN RAISE EXCEPTION 'rating cancellation is final'; END IF;
        IF OLD.cancelled_at IS NOT NULL AND NEW.sent_at IS DISTINCT FROM OLD.sent_at
        THEN RAISE EXCEPTION 'cancelled rating cannot be delivered'; END IF;
        IF NEW.sent_at IS NOT NULL AND NEW.expires_at IS DISTINCT FROM NEW.sent_at + interval '7 days'
        THEN RAISE EXCEPTION 'rating expiry must be seven days after sending'; END IF;
        RETURN NEW;
    END IF;
    PERFORM id FROM conversations_conversation
        WHERE id = NEW.conversation_id AND organization_id = NEW.organization_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'rating conversation unavailable'; END IF;
    SELECT * INTO completion FROM conversations_conversationevent
        WHERE id = NEW.completion_id AND organization_id = NEW.organization_id;
    IF NOT FOUND OR completion.event_type <> 'CLOSED'
        OR completion.conversation_id <> NEW.conversation_id
    THEN RAISE EXCEPTION 'rating completion mismatch'; END IF;
    IF NOT chatballs.valid_rating_scale(NEW.scale) OR length(btrim(NEW.text)) = 0
        OR length(NEW.text) > 4000 OR NEW.delay_seconds > 604800
    THEN RAISE EXCEPTION 'invalid rating snapshot'; END IF;
    NEW.due_at := completion.occurred_at + NEW.delay_seconds * interval '1 second';
    SELECT session.id INTO NEW.delivery_session_id
        FROM webchat_websession session JOIN conversations_conversation conversation
          ON conversation.id = NEW.conversation_id
        WHERE session.organization_id = NEW.organization_id
          AND session.connection_id = conversation.connection_id
          AND session.identity_id IN (SELECT id FROM conversations_connectionidentity
              WHERE contact_id = conversation.contact_id AND connection_id = conversation.connection_id)
          AND session.widget_id::text = conversation.transport_meta->>'webChatWidgetId'
        ORDER BY session.id LIMIT 1;
    -- Typed facts retain historical responders even after membership deletion.
    -- Existing public messages cover replies predating journal availability.
    SELECT COALESCE(jsonb_agg(user_id ORDER BY user_id), '[]'::jsonb)
        INTO NEW.responder_ids FROM (
            SELECT initiated_by_id AS user_id FROM conversations_conversationevent
            WHERE conversation_id = NEW.conversation_id AND organization_id = NEW.organization_id
              AND sequence < completion.sequence AND event_type = 'PUBLIC_REPLY'
              AND actor_kind = 'HUMAN' AND initiated_by_id IS NOT NULL
            UNION
            SELECT author_user_id FROM conversations_message
            WHERE conversation_id = NEW.conversation_id AND organization_id = NEW.organization_id
              AND created_at <= completion.occurred_at AND author_type = 'OPERATOR'
              AND system_event = '' AND kind IN ('', 'file', 'voice', 'contact_request')
              AND author_user_id IS NOT NULL
        ) responders;
    RETURN NEW;
END $$;
CREATE TRIGGER rating_request_guard BEFORE INSERT OR UPDATE ON ratings_ratingrequest
    FOR EACH ROW EXECUTE FUNCTION chatballs.guard_rating_request();

CREATE FUNCTION chatballs.guard_customer_rating() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE target ratings_ratingrequest%%ROWTYPE;
BEGIN
    IF TG_OP = 'UPDATE' THEN RAISE EXCEPTION 'customer rating is immutable'; END IF;
    SELECT * INTO target FROM ratings_ratingrequest
        WHERE id = NEW.request_id AND organization_id = NEW.organization_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'rating request unavailable'; END IF;
    IF target.sent_at IS NULL OR target.cancelled_at IS NOT NULL
        OR target.expires_at <= clock_timestamp()
    THEN RAISE EXCEPTION 'rating request is inactive'; END IF;
    IF NOT EXISTS (SELECT 1 FROM jsonb_array_elements(target.scale) choice
                   WHERE choice->>'value' = NEW.value)
    THEN RAISE EXCEPTION 'rating value is outside the snapshot'; END IF;
    IF length(NEW.comment) > 2000 THEN RAISE EXCEPTION 'rating comment is too long'; END IF;
    NEW.received_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER customer_rating_guard BEFORE INSERT OR UPDATE ON ratings_customerrating
    FOR EACH ROW EXECUTE FUNCTION chatballs.guard_customer_rating();

CREATE VIEW chatballs.rating_request_directory WITH (security_barrier = true) AS
    SELECT id AS resource_id, organization_id, credential_hash AS lookup_key
    FROM ratings_ratingrequest WHERE sent_at IS NOT NULL AND cancelled_at IS NULL
      AND expires_at > clock_timestamp();
ALTER VIEW chatballs.rating_request_directory OWNER TO chatballs_schema;
REVOKE ALL ON chatballs.rating_request_directory FROM PUBLIC;
GRANT SELECT ON chatballs.rating_request_directory TO chatballs_runtime_app;
"""


def forward(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(f"""
            ALTER TABLE {table} OWNER TO chatballs_schema;
            ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;
            ALTER TABLE {table} FORCE ROW LEVEL SECURITY;
            REVOKE ALL ON TABLE {table} FROM PUBLIC;
            GRANT ALL ON TABLE {table} TO chatballs_schema;
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {table} TO chatballs_runtime_app;
            GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO chatballs_runtime_app;
            CREATE POLICY chatballs_schema_access ON {table}
                FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);
            CREATE POLICY chatballs_tenant_isolation ON {table}
                FOR ALL TO chatballs_runtime_app
                USING (organization_id = chatballs.current_organization_id())
                WITH CHECK (organization_id = chatballs.current_organization_id());
        """)
    for table, parent, column in (
        ("ratings_ratingrequest", "conversations_conversation", "conversation_id"),
        ("ratings_ratingrequest", "conversations_conversationevent", "completion_id"),
        ("ratings_customerrating", "ratings_ratingrequest", "request_id"),
    ):
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER rating_{column}_tenant AFTER INSERT OR UPDATE ON {table}
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)
    schema_editor.execute(GUARDS)


def backward(apps, schema_editor):
    schema_editor.execute("DROP VIEW chatballs.rating_request_directory")
    schema_editor.execute("DROP TRIGGER rating_request_guard ON ratings_ratingrequest")
    schema_editor.execute("DROP TRIGGER customer_rating_guard ON ratings_customerrating")
    schema_editor.execute("DROP FUNCTION chatballs.guard_rating_request()")
    schema_editor.execute("DROP FUNCTION chatballs.guard_customer_rating()")
    schema_editor.execute("DROP FUNCTION chatballs.valid_rating_scale(jsonb)")
    for table, columns in (
        ("ratings_ratingrequest", ("conversation_id", "completion_id")),
        ("ratings_customerrating", ("request_id",)),
    ):
        for column in columns:
            schema_editor.execute(f"DROP TRIGGER rating_{column}_tenant ON {table}")
    for table in TABLES:
        schema_editor.execute(f"""
            DROP POLICY chatballs_tenant_isolation ON {table};
            DROP POLICY chatballs_schema_access ON {table};
            ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
            REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app;
            REVOKE ALL ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app;
        """)


class Migration(migrations.Migration):
    dependencies = [("ratings", "0001_initial"), ("tenancy", "0045_merge_domain_events")]
    operations = [migrations.RunPython(forward, backward)]
