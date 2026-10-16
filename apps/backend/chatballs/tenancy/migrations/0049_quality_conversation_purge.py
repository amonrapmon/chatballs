"""Delete quality evidence only as a subtree of a physically deleted dialog."""

from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION chatballs.quality_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND pg_trigger_depth() > 1 THEN
        IF TG_TABLE_NAME IN ('conversations_qualityresult', 'conversations_qualityjoboperation') THEN
            IF NOT EXISTS (SELECT 1 FROM conversations_qualityjob WHERE id = OLD.job_id)
                THEN RETURN OLD; END IF;
        ELSIF TG_TABLE_NAME = 'conversations_qualitycorrection' THEN
            IF NOT EXISTS (SELECT 1 FROM conversations_qualityresult WHERE id = OLD.result_id)
                THEN RETURN OLD; END IF;
        END IF;
    END IF;
    RAISE EXCEPTION 'Quality snapshot is immutable' USING ERRCODE = '23514';
END;
$$;
CREATE FUNCTION chatballs.quality_purge_subtree() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'conversations_conversation' THEN
        DELETE FROM conversations_qualityjob WHERE conversation_id = OLD.id;
    ELSIF TG_TABLE_NAME = 'conversations_qualityjob' THEN
        IF EXISTS (SELECT 1 FROM conversations_conversation WHERE id = OLD.conversation_id) THEN
            RAISE EXCEPTION 'Quality snapshot is immutable' USING ERRCODE = '23514';
        END IF;
        DELETE FROM conversations_qualityjoboperation WHERE job_id = OLD.id;
        DELETE FROM conversations_qualityresult WHERE job_id = OLD.id;
    ELSIF TG_TABLE_NAME = 'conversations_qualityresult' THEN
        DELETE FROM conversations_qualitycorrection WHERE result_id = OLD.id;
    END IF;
    RETURN OLD;
END;
$$;
CREATE TRIGGER quality_dialog_purge AFTER DELETE ON conversations_conversation
FOR EACH ROW EXECUTE FUNCTION chatballs.quality_purge_subtree();
CREATE TRIGGER quality_job_purge AFTER DELETE ON conversations_qualityjob
FOR EACH ROW EXECUTE FUNCTION chatballs.quality_purge_subtree();
CREATE TRIGGER quality_result_purge AFTER DELETE ON conversations_qualityresult
FOR EACH ROW EXECUTE FUNCTION chatballs.quality_purge_subtree();
"""

REVERSE = """
DROP TRIGGER quality_dialog_purge ON conversations_conversation;
DROP TRIGGER quality_job_purge ON conversations_qualityjob;
DROP TRIGGER quality_result_purge ON conversations_qualityresult;
DROP FUNCTION chatballs.quality_purge_subtree();
CREATE OR REPLACE FUNCTION chatballs.quality_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Quality snapshot is immutable' USING ERRCODE = '23514';
END;
$$;
"""


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0048_merge_quality_reporting_diagnostics"),
                    ("conversations", "0038_quality_conversation_purge")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
