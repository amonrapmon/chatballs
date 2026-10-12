"""Template libraries have tenant RLS and immutable membership ownership."""

from django.db import migrations

TABLES = (
    "conversations_replytemplatecategory", "conversations_replytemplatetag",
    "conversations_replytemplatetaglink", "conversations_replytemplatemanagementgrant",
)
SCOPED = ("conversations_replytemplate", *TABLES[:2])
RELATIONS = (
    (SCOPED[0], "identity_employeeprofile", "owner_id"),
    (TABLES[0], "identity_employeeprofile", "owner_id"),
    (TABLES[1], "identity_employeeprofile", "owner_id"),
    (TABLES[2], SCOPED[0], "template_id"),
    (TABLES[2], TABLES[1], "tag_id"),
    (TABLES[3], "identity_employeeprofile", "membership_id"),
)

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

FUNCTIONS = """
CREATE FUNCTION chatballs.template_owner_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$ BEGIN
    IF NEW.organization_id IS DISTINCT FROM OLD.organization_id
       OR NEW.owner_id IS DISTINCT FROM OLD.owner_id THEN
        RAISE EXCEPTION 'template library ownership is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION chatballs.template_category_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE category_org bigint; category_owner bigint;
BEGIN
    IF NEW.category_id IS NOT NULL THEN
        SELECT organization_id, owner_id INTO category_org, category_owner
        FROM conversations_replytemplatecategory WHERE id = NEW.category_id;
        IF category_org IS DISTINCT FROM NEW.organization_id
           OR category_owner IS DISTINCT FROM NEW.owner_id THEN
            RAISE EXCEPTION 'template category library mismatch' USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION chatballs.template_tag_scope() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp AS $$
DECLARE template_owner bigint; tag_owner bigint;
BEGIN
    SELECT owner_id INTO template_owner FROM conversations_replytemplate WHERE id = NEW.template_id;
    SELECT owner_id INTO tag_owner FROM conversations_replytemplatetag WHERE id = NEW.tag_id;
    IF template_owner IS DISTINCT FROM tag_owner THEN
        RAISE EXCEPTION 'template tag library mismatch' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;

ALTER FUNCTION chatballs.template_owner_immutable() OWNER TO chatballs_schema;
ALTER FUNCTION chatballs.template_category_scope() OWNER TO chatballs_schema;
ALTER FUNCTION chatballs.template_tag_scope() OWNER TO chatballs_schema;
REVOKE ALL ON FUNCTION chatballs.template_owner_immutable() FROM PUBLIC;
REVOKE ALL ON FUNCTION chatballs.template_category_scope() FROM PUBLIC;
REVOKE ALL ON FUNCTION chatballs.template_tag_scope() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION chatballs.template_owner_immutable() TO chatballs_runtime_app;
GRANT EXECUTE ON FUNCTION chatballs.template_category_scope() TO chatballs_runtime_app;
GRANT EXECUTE ON FUNCTION chatballs.template_tag_scope() TO chatballs_runtime_app;
"""


def apply_guards(apps, schema_editor):
    for table in TABLES:
        schema_editor.execute(RLS.format(table=table))
    schema_editor.execute(FUNCTIONS)
    for table in SCOPED:
        schema_editor.execute(f"""
            CREATE TRIGGER template_owner_immutable BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION chatballs.template_owner_immutable();
        """)
    for table, parent, column in RELATIONS:
        schema_editor.execute(f"""
            CREATE CONSTRAINT TRIGGER template_{column}_tenant
            AFTER INSERT OR UPDATE ON {table} DEFERRABLE INITIALLY IMMEDIATE
            FOR EACH ROW EXECUTE FUNCTION chatballs.enforce_tenant_fk('{parent}', '{column}');
        """)
    schema_editor.execute("""
        CREATE CONSTRAINT TRIGGER template_category_scope
        AFTER INSERT OR UPDATE ON conversations_replytemplate
        DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION chatballs.template_category_scope();
        CREATE CONSTRAINT TRIGGER template_tag_scope
        AFTER INSERT OR UPDATE ON conversations_replytemplatetaglink
        DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION chatballs.template_tag_scope();
    """)


def remove_guards(apps, schema_editor):
    schema_editor.execute("DROP TRIGGER template_category_scope ON conversations_replytemplate")
    schema_editor.execute("DROP TRIGGER template_tag_scope ON conversations_replytemplatetaglink")
    for table, _, column in RELATIONS:
        schema_editor.execute(f"DROP TRIGGER template_{column}_tenant ON {table}")
    for table in SCOPED:
        schema_editor.execute(f"DROP TRIGGER template_owner_immutable ON {table}")
    for function in ("template_owner_immutable", "template_category_scope", "template_tag_scope"):
        schema_editor.execute(f"DROP FUNCTION chatballs.{function}()")
    for table in TABLES:
        schema_editor.execute(f"DROP POLICY chatballs_tenant_isolation ON {table}")
        schema_editor.execute(f"DROP POLICY chatballs_schema_access ON {table}")
        schema_editor.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        schema_editor.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
        schema_editor.execute(f"REVOKE ALL ON TABLE {table} FROM chatballs_runtime_app")
        schema_editor.execute(f"REVOKE USAGE, SELECT ON SEQUENCE {table}_id_seq FROM chatballs_runtime_app")


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0042_participant_guards"),
        ("conversations", "0032_template_libraries"),
    ]
    operations = [migrations.RunPython(apply_guards, remove_guards)]
