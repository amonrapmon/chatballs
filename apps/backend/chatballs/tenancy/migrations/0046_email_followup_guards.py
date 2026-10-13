"""A closed thread is authority only for its exact successor route."""

from importlib import import_module

from django.db import migrations

BASE = import_module("chatballs.tenancy.migrations.0043_email_continuation_guards")
FOLLOWUP_CHECK = """
        IF TG_OP = 'UPDATE' AND NEW.previous_thread_id IS DISTINCT FROM OLD.previous_thread_id
           AND NEW.previous_thread_id IS NOT NULL THEN
            RAISE EXCEPTION 'email predecessor cannot be replaced';
        END IF;
        IF TG_OP = 'INSERT' AND NEW.previous_thread_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM conversations_emailthread p
                JOIN conversations_conversation predecessor_conv ON predecessor_conv.id = p.conversation_id
                JOIN conversations_conversation successor_conv ON successor_conv.id = NEW.conversation_id
                WHERE p.id = NEW.previous_thread_id AND p.organization_id = NEW.organization_id
                    AND p.connection_id = NEW.connection_id AND p.recipient = NEW.recipient
                    AND p.subject = NEW.subject AND predecessor_conv.lifecycle <> 'OPEN'
                    AND successor_conv.previous_conversation_id = predecessor_conv.id
                    AND successor_conv.contact_id = predecessor_conv.contact_id
                    AND successor_conv.channel_id = predecessor_conv.channel_id AND successor_conv.connection_id = predecessor_conv.connection_id
            ) THEN
                RAISE EXCEPTION 'email followup route must match closed predecessor';
            END IF;
        END IF;
"""


def install(apps, schema_editor):
    sql = BASE.INTEGRITY.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION")
    sql = sql.replace("        IF TG_OP = 'INSERT' THEN", FOLLOWUP_CHECK + "        IF TG_OP = 'INSERT' AND NEW.previous_thread_id IS NULL THEN")
    schema_editor.execute(sql)
    schema_editor.execute("""
        CREATE CONSTRAINT TRIGGER email_previous_thread_tenant
        AFTER INSERT OR UPDATE ON conversations_emailthread
        DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
        chatballs.enforce_tenant_fk('conversations_emailthread', 'previous_thread_id');
        DROP TRIGGER zz_email_integrity ON conversations_emailthread;
        CREATE TRIGGER zz_email_integrity AFTER INSERT OR UPDATE ON conversations_emailthread
        FOR EACH ROW EXECUTE FUNCTION chatballs.enforce_email_continuation(
            'organization_id,conversation_id,connection_id,recipient');
    """)


def uninstall(apps, schema_editor):
    schema_editor.execute(BASE.INTEGRITY.replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION"))
    schema_editor.execute("""
        DROP TRIGGER email_previous_thread_tenant ON conversations_emailthread;
        DROP TRIGGER zz_email_integrity ON conversations_emailthread;
        CREATE TRIGGER zz_email_integrity AFTER INSERT OR UPDATE ON conversations_emailthread
        FOR EACH ROW EXECUTE FUNCTION chatballs.enforce_email_continuation(
            'organization_id,conversation_id,connection_id,recipient');
    """)


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0045_merge_visitor_observations"),
        ("conversations", "0034_email_thread_followup"),
    ]
    operations = [migrations.RunPython(install, uninstall)]
