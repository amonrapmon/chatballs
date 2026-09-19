from django.db import migrations


FORWARD_SQL = """
CREATE OR REPLACE VIEW chatballs.gateway_integration_directory
WITH (security_barrier = true) AS
    SELECT integration.id AS resource_id,
           integration.organization_id,
           integration.id::text AS lookup_key
    FROM integrations_integration integration
    WHERE integration.provider = 'GATEWAY';
ALTER VIEW chatballs.gateway_integration_directory OWNER TO chatballs_schema;
REVOKE ALL ON chatballs.gateway_integration_directory FROM PUBLIC;
GRANT SELECT ON chatballs.gateway_integration_directory
    TO chatballs_runtime_app, chatballs_runtime_platform;
"""

REVERSE_SQL = """
DROP VIEW IF EXISTS chatballs.gateway_integration_directory;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0010_integration_gateway"),
        ("tenancy", "0037_queue_policy_guards"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
