from unittest.mock import patch

import pytest

from chatballs.identity.instance_settings import InstanceSettings
from chatballs.updates.announcement_subscriber import _configuration
from chatballs.updates.check_in import check_in_if_due
from chatballs.updates.check_in_state import CheckInState, announcement_snapshot
from chatballs.updates.services import check_for_updates


@pytest.mark.django_db
@pytest.mark.parametrize("settings_exist", [False, True])
def test_default_skips_automatic_github_check(settings_exist, settings):
    settings.CHATBALLS_UPDATE_REPO = "example/chatballs"
    if settings_exist:
        InstanceSettings.load()

    with patch("urllib.request.urlopen", side_effect=AssertionError("Unexpected GitHub request")):
        assert check_for_updates().checked_at is None


@pytest.mark.django_db
def test_first_check_in_stays_off_after_settings_are_persisted():
    with patch("chatballs.updates.check_in.send_check_in", side_effect=AssertionError("Unexpected check-in")):
        check_in_if_due()
        check_in_if_due()

    assert InstanceSettings.objects.get().external_checks_enabled is False
    assert not CheckInState.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("settings_exist", [False, True])
def test_default_skips_sse_and_reports_announcements_disabled(settings_exist):
    if settings_exist:
        InstanceSettings.load()

    assert _configuration() is None
    assert announcement_snapshot()["enabled"] is False
    assert not CheckInState.objects.exists()
