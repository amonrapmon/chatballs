"""Capture the exact block instant atomically, including admin/SQL transitions."""

from django.db import migrations

FORWARD = """
CREATE FUNCTION chatballs.stop_blocked_work_status() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    IF NEW.blocked_at IS NOT NULL AND NEW.blocked_at IS DISTINCT FROM OLD.blocked_at THEN
        UPDATE public.identity_workstatusoperation
        SET stopped_at = NEW.blocked_at
        WHERE membership_id = NEW.id AND organization_id = NEW.organization_id
          AND version = NEW.work_status_version AND previous_status <> status
          AND stopped_at IS NULL AND changed_at <= NEW.blocked_at;
    END IF;
    RETURN NEW;
END $$;
REVOKE ALL ON FUNCTION chatballs.stop_blocked_work_status() FROM PUBLIC;
CREATE TRIGGER work_status_block_stop AFTER UPDATE OF blocked_at ON identity_employeeprofile
    FOR EACH ROW EXECUTE FUNCTION chatballs.stop_blocked_work_status();
-- These are actual stored block instants, not reconstructed status history.
UPDATE identity_workstatusoperation operation SET stopped_at = member.blocked_at
FROM identity_employeeprofile member
WHERE operation.membership_id = member.id AND operation.organization_id = member.organization_id
  AND operation.version = member.work_status_version AND operation.previous_status <> operation.status
  AND member.blocked_at IS NOT NULL AND operation.changed_at <= member.blocked_at
  AND operation.stopped_at IS NULL;
"""
REVERSE = """
DROP TRIGGER work_status_block_stop ON identity_employeeprofile;
DROP FUNCTION chatballs.stop_blocked_work_status();
"""


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0046_merge_domain_event_guards"), ("identity", "0045_work_status_stop")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
