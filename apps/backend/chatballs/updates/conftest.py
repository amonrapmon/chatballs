import pytest

from chatballs.identity.instance_settings import InstanceSettings


@pytest.fixture
def external_checks_enabled(db):
    return InstanceSettings.objects.create(external_checks_enabled=True)
