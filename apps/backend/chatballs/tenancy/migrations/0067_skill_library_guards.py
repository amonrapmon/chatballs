"""Skill library: runtime RLS, tenant FK guards and immutable ownership."""

from django.db import migrations

TABLES = ("ai_skill", "ai_agentskill", "ai_skillrequest")


def forwards(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(f"""
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
        """)
    schema_editor.execute("""
        REVOKE UPDATE, DELETE ON ai_skillrequest FROM chatballs_runtime_app;
        CREATE FUNCTION chatballs.skill_owner_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
                OR NEW.public_id IS DISTINCT FROM OLD.public_id THEN
                RAISE EXCEPTION 'skill ownership is immutable' USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
        END $$;
        ALTER FUNCTION chatballs.skill_owner_immutable() OWNER TO chatballs_schema;
        REVOKE ALL ON FUNCTION chatballs.skill_owner_immutable() FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION chatballs.skill_owner_immutable() TO chatballs_runtime_app;
        CREATE TRIGGER skill_owner_immutable BEFORE UPDATE ON ai_skill
            FOR EACH ROW EXECUTE FUNCTION chatballs.skill_owner_immutable();
        ALTER TABLE ai_skill ADD CONSTRAINT skill_valid_text CHECK (
            length(btrim(name)) > 0 AND length(btrim(description)) > 0
            AND length(btrim(instruction, E' \\n\\r\\t')) > 0 AND length(instruction) <= 32768
        );
    """)
    for parent, column in (("ai_skill", "skill_id"), ("ai_aiagent", "agent_id")):
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER ai_agentskill_{column}_tenant
            AFTER INSERT OR UPDATE ON ai_agentskill
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)
    for column in ("created_by_id", "updated_by_id"):
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER ai_skill_{column}_tenant
            AFTER INSERT OR UPDATE ON ai_skill
            DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
            chatballs.enforce_tenant_user('{column}');
        """)


def backwards(apps, schema_editor):
    schema_editor.execute("DROP TRIGGER skill_owner_immutable ON ai_skill")
    schema_editor.execute("DROP FUNCTION chatballs.skill_owner_immutable()")
    schema_editor.execute("ALTER TABLE ai_skill DROP CONSTRAINT skill_valid_text")
    for table, columns in (("ai_agentskill", ("skill_id", "agent_id")), ("ai_skill", ("created_by_id", "updated_by_id"))):
        for column in columns:
            schema_editor.execute(f"DROP TRIGGER {table}_{column}_tenant ON {table}")
    for table in TABLES:
        schema_editor.execute(f"""
            DROP POLICY chatballs_tenant_isolation ON {table};
            DROP POLICY chatballs_schema_access ON {table};
            ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY;
            ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;
            REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app;
            REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app;
        """)


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0066_merge_email_ui_rules"), ("ai", "0028_skill_library")]
    operations = [migrations.RunPython(forwards, backwards)]
