"""Quality snapshots are tenant-owned and immutable even through bulk SQL."""

from django.db import migrations

PREFIX = "conversations_quality"
RELATIONS = {
    "criteriaversion": (("identity_employeeprofile", "created_by_id"),),
    "settings": ((PREFIX + "criteriaversion", "current_version_id"),),
    "job": (("conversations_conversation", "conversation_id"),
            (PREFIX + "criteriaversion", "criteria_version_id")),
    "result": ((PREFIX + "job", "job_id"),),
    "joboperation": ((PREFIX + "job", "job_id"),),
    "correction": ((PREFIX + "result", "result_id"), ("identity_employeeprofile", "author_id")),
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

IMMUTABLE = """
CREATE FUNCTION chatballs.quality_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Quality snapshot is immutable' USING ERRCODE = '23514';
END;
$$;
CREATE FUNCTION chatballs.quality_job_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'WAITING' THEN
            RAISE EXCEPTION 'Quality job must start waiting' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    IF (to_jsonb(NEW) - ARRAY['state','error_code','started_at','finished_at'])
       IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['state','error_code','started_at','finished_at']) THEN
        RAISE EXCEPTION 'Quality job snapshot is immutable' USING ERRCODE = '23514';
    END IF;
    IF OLD.state IN ('SUCCEEDED', 'FAILED') AND NEW IS DISTINCT FROM OLD THEN
        RAISE EXCEPTION 'Quality job is terminal' USING ERRCODE = '23514';
    END IF;
    IF NEW.state <> OLD.state AND NOT (
        (OLD.state = 'WAITING' AND NEW.state = 'RUNNING') OR
        (OLD.state = 'RUNNING' AND NEW.state IN ('SUCCEEDED', 'FAILED'))
    ) THEN
        RAISE EXCEPTION 'Invalid quality job transition' USING ERRCODE = '23514';
    END IF;
    IF NEW.state = 'SUCCEEDED' AND NOT EXISTS (
        SELECT 1 FROM conversations_qualityresult WHERE job_id = NEW.id
    ) THEN
        RAISE EXCEPTION 'Quality result is required' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$;
"""


def apply_guards(apps, schema_editor):
    for suffix, relations in RELATIONS.items():
        table = PREFIX + suffix
        schema_editor.execute(RLS.format(table=table))
        for parent, column in relations:
            schema_editor.execute(f"""
                CREATE CONSTRAINT TRIGGER quality_{suffix}_{column}_tenant
                AFTER INSERT OR UPDATE ON {table}
                DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
                chatballs.enforce_tenant_fk('{parent}', '{column}');
            """)
    schema_editor.execute(IMMUTABLE)
    for suffix in ("criteriaversion", "result", "correction", "joboperation"):
        schema_editor.execute(f"""
            CREATE TRIGGER quality_{suffix}_immutable BEFORE UPDATE OR DELETE
            ON {PREFIX + suffix} FOR EACH ROW EXECUTE FUNCTION chatballs.quality_immutable();
        """)
    schema_editor.execute(f"""
        CREATE TRIGGER quality_job_snapshot BEFORE INSERT OR UPDATE ON {PREFIX}job
        FOR EACH ROW EXECUTE FUNCTION chatballs.quality_job_guard();
    """)


def remove_guards(apps, schema_editor):
    schema_editor.execute(f"DROP TRIGGER quality_job_snapshot ON {PREFIX}job")
    for suffix in ("criteriaversion", "result", "correction", "joboperation"):
        schema_editor.execute(f"DROP TRIGGER quality_{suffix}_immutable ON {PREFIX + suffix}")
    schema_editor.execute("DROP FUNCTION chatballs.quality_job_guard()")
    schema_editor.execute("DROP FUNCTION chatballs.quality_immutable()")
    for suffix, relations in RELATIONS.items():
        table = PREFIX + suffix
        for _, column in relations:
            schema_editor.execute(f"DROP TRIGGER quality_{suffix}_{column}_tenant ON {table}")
        schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
        schema_editor.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app")


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0042_participant_guards"), ("conversations", "0032_quality_data")]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
