from copy import deepcopy

from django.db import DatabaseError, transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from chatballs.identity.models import EmployeeRole
from chatballs.tenancy.context import TenantContext

from .models import QualityCriteriaVersion, QualitySettings
from .test_base import CRITERIA, QualityTestBase


class CriteriaTests(QualityTestBase):
    def test_absent_settings_and_unconfigured_settings_cannot_start_analysis(self):
        self.assertFalse(QualitySettings.objects.exists())
        with self.assertRaises(ValidationError):
            self.job()
        settings = QualitySettings.objects.create(organization=self.organization)
        self.assertFalse(settings.enabled)
        self.assertIsNone(settings.current_version)
        with self.assertRaises(ValidationError):
            self.configure(criteria=None)
        with self.assertRaises(DatabaseError), transaction.atomic():
            QualitySettings.objects.filter(pk=settings.pk).update(enabled=True)

    def test_criteria_and_scales_must_be_complete_before_enabling(self):
        for criteria in ([], None, {}, [{"code": "a"}],
                         [{**CRITERIA[0], "scale": []}], [{**CRITERIA[0], "description": " "}],
                         CRITERIA * 2, [{**CRITERIA[0], "scale": [False]}],
                         [{**CRITERIA[0], "scale": [1, 1]}], [{**CRITERIA[0], "scale": [float("nan")]}]):
            with self.subTest(criteria=criteria), self.assertRaises(ValidationError):
                self.configure(criteria=criteria)
        self.assertFalse(QualityCriteriaVersion.objects.exists())

    def test_new_criteria_version_keeps_previous_data_and_explicit_disable(self):
        first = self.configure(enabled=False)
        self.assertFalse(first.enabled)
        previous = first.current_version
        self.configure(criteria=None)
        changed = deepcopy(CRITERIA)
        changed[0]["scale"] = ["low", "high"]
        current = self.configure(criteria=changed)
        self.assertEqual(current.current_version.version, 2)
        previous.refresh_from_db()
        self.assertEqual(previous.criteria, CRITERIA)
        self.assertEqual(previous.created_by, self.context.membership)
        self.assertIsNotNone(previous.created_at)
        self.assertFalse(self.configure(enabled=False, criteria=None).enabled)
        with self.assertRaises(ValidationError):
            self.job()

    def test_report_metadata_is_validated_without_guessing_positive_values(self):
        for changes in ({"name": " "}, {"name": "x" * 201}, {"reporting": {}}, {"reporting": {"positiveValue": 1}},
                        {"reporting": {"positiveValue": "Missing"}}, {"other": "unsupported"}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError):
                self.configure(criteria=[{**CRITERIA[0], **changes}])
        criterion = {"code": "resolution", "description": "Resolved", "name": "Resolution",
                     "scale": ["Yes", "No"], "reporting": {"positiveValue": "Yes"}}
        self.assertEqual(self.configure(criteria=[criterion]).current_version.criteria, [criterion])

    def test_only_owner_admin_can_configure_without_affecting_other_tenant(self):
        for role in (EmployeeRole.OWNER, EmployeeRole.ADMIN):
            self.configure(context=TenantContext.for_membership(self.members[role]))
        with self.assertRaises(PermissionDenied):
            self.configure(context=TenantContext.for_membership(self.members[EmployeeRole.EMPLOYEE]))
        self.assertFalse(QualitySettings.objects.filter(organization=self.foreign).exists())
