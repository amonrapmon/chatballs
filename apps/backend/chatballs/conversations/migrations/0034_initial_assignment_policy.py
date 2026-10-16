"""Owner decision: all work statuses allow assignment until explicitly changed."""

from django.db import migrations


FORWARD = """
INSERT INTO conversations_assignmentpolicy
    (organization_id, ready, busy, break_allowed, unavailable)
SELECT id, true, true, true, true FROM identity_organization
ON CONFLICT (organization_id) DO NOTHING;

CREATE FUNCTION chatballs.initialize_assignment_policy() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
BEGIN
    INSERT INTO public.conversations_assignmentpolicy
        (organization_id, ready, busy, break_allowed, unavailable)
    VALUES (NEW.id, true, true, true, true);
    RETURN NEW;
END $$;
ALTER FUNCTION chatballs.initialize_assignment_policy() OWNER TO chatballs_schema;
REVOKE ALL ON FUNCTION chatballs.initialize_assignment_policy() FROM PUBLIC;
CREATE TRIGGER organization_assignment_policy
    AFTER INSERT ON identity_organization
    FOR EACH ROW EXECUTE FUNCTION chatballs.initialize_assignment_policy();
"""

BACKWARD = """
DROP TRIGGER organization_assignment_policy ON identity_organization;
DROP FUNCTION chatballs.initialize_assignment_policy();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("conversations", "0033_assignment_transfer"),
        ("tenancy", "0046_assignment_transfer_guards"),
    ]
    operations = [migrations.RunSQL(FORWARD, BACKWARD)]
