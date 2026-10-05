# Иконки виджета (webchat_widgetasset): tenant-таблица с organization_id, RLS и
# триггерами связей по образцу tenancy/0027. Иконка показывается на чужом сайте
# без сессии, поэтому строка попадает в ingress-каталог: публичная отдача
# находит организацию по непредсказуемому public_id.
from django.db import migrations

TABLE = "webchat_widgetasset"

FORWARD_SQL = f"""
ALTER TABLE {TABLE} OWNER TO chatballs_schema;
ALTER TABLE {TABLE} ENABLE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} FORCE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE {TABLE} FROM PUBLIC;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE {TABLE} TO chatballs_runtime_app;
GRANT ALL ON TABLE {TABLE} TO chatballs_schema;
GRANT USAGE, SELECT ON SEQUENCE {TABLE}_id_seq
    TO chatballs_runtime_app, chatballs_runtime_platform, chatballs_schema;
DROP POLICY IF EXISTS chatballs_tenant_isolation ON {TABLE};
CREATE POLICY chatballs_tenant_isolation ON {TABLE}
    FOR ALL TO chatballs_runtime_app
    USING (organization_id = chatballs.current_organization_id())
    WITH CHECK (organization_id = chatballs.current_organization_id());
DROP POLICY IF EXISTS chatballs_schema_access ON {TABLE};
CREATE POLICY chatballs_schema_access ON {TABLE}
    FOR ALL TO chatballs_schema USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS webchat_asset_integration ON {TABLE};
CREATE CONSTRAINT TRIGGER webchat_asset_integration
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
chatballs.enforce_tenant_fk('integrations_integration', 'integration_id');

DROP TRIGGER IF EXISTS webchat_asset_user ON {TABLE};
CREATE CONSTRAINT TRIGGER webchat_asset_user
AFTER INSERT OR UPDATE ON {TABLE}
DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION
chatballs.enforce_tenant_user('uploaded_by_id');

CREATE OR REPLACE VIEW chatballs.widget_asset_directory
WITH (security_barrier = true) AS
    SELECT asset.id AS resource_id,
           asset.organization_id,
           asset.public_id::text AS lookup_key
    FROM {TABLE} asset;
ALTER VIEW chatballs.widget_asset_directory OWNER TO chatballs_schema;
REVOKE ALL ON chatballs.widget_asset_directory FROM PUBLIC;
GRANT SELECT ON chatballs.widget_asset_directory
    TO chatballs_runtime_app, chatballs_runtime_platform;
"""

REVERSE_SQL = f"""
DROP VIEW IF EXISTS chatballs.widget_asset_directory;
DROP TRIGGER IF EXISTS webchat_asset_user ON {TABLE};
DROP TRIGGER IF EXISTS webchat_asset_integration ON {TABLE};
DROP POLICY IF EXISTS chatballs_tenant_isolation ON {TABLE};
DROP POLICY IF EXISTS chatballs_schema_access ON {TABLE};
ALTER TABLE {TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE {TABLE} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0037_queue_policy_guards"),
        ("webchat", "0006_widget_asset"),
    ]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
