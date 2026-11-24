import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

FORK_122 = [("identity", "0049_external_execution_configuration"), ("updates", "0001_initial")]
UPSTREAM_124 = [("identity", "0051_membership_dismissal"), ("updates", "0007_announcement_retry")]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(("before", "old_policy", "expected"), [
    (FORK_122, {}, (False, 0)),
    (UPSTREAM_124, {}, (False, 0)),
    (UPSTREAM_124, {"external_checks_enabled": True, "external_checks_revision": 2}, (True, 2)),
    (UPSTREAM_124, {"external_checks_enabled": False, "external_checks_revision": 1}, (False, 1)),
])
def test_external_checks_upgrade_preserves_recorded_choices(before, old_policy, expected):
    executor = MigrationExecutor(connection)
    latest = executor.loader.graph.leaf_nodes()
    executor.migrate(before)
    try:
        old_settings = executor.loader.project_state(before).apps.get_model("identity", "InstanceSettings")
        old_settings.objects.create(pk=1, public_host="existing.example.test", **old_policy)

        MigrationExecutor(connection).migrate(latest)
        new_settings = executor.loader.project_state(latest).apps.get_model("identity", "InstanceSettings")
        row = new_settings.objects.get(pk=1)
        assert (row.external_checks_enabled, row.external_checks_revision) == expected
        assert row.public_host == "existing.example.test"
    finally:
        MigrationExecutor(connection).migrate(latest)
