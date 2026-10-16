from django.core.exceptions import ValidationError
from django.db import DatabaseError, connection, transaction

from chatballs.conversations.template_models import (
    ReplyTemplate,
    ReplyTemplateCategory,
    ReplyTemplateManagementGrant,
    ReplyTemplateTag,
    ReplyTemplateTagLink,
)
from chatballs.conversations.template_test_base import TemplateTestBase
from chatballs.tenancy.database import tenant_atomic


class TemplateGuardTests(TemplateTestBase):
    models = (ReplyTemplate, ReplyTemplateCategory, ReplyTemplateTag, ReplyTemplateTagLink, ReplyTemplateManagementGrant)

    @staticmethod
    def app_role():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL ROLE chatballs_runtime_app")

    def library(self, organization, membership):
        category = ReplyTemplateCategory.objects.create(organization=organization, owner=membership, name="Category")
        tag = ReplyTemplateTag.objects.create(organization=organization, owner=membership, name="Tag")
        template = ReplyTemplate.objects.create(
            organization=organization, owner=membership, category=category, title="Template", text="Text",
        )
        link = ReplyTemplateTagLink.objects.create(organization=organization, template=template, tag=tag)
        grant = ReplyTemplateManagementGrant.objects.create(organization=organization, membership=membership)
        return template, category, tag, link, grant

    def test_rls_denies_no_context_and_foreign_tenants_under_real_runtime_role(self):
        local = self.library(self.organization, self.employee)
        foreign = self.library(self.foreign, self.foreign_member)
        with transaction.atomic():
            self.app_role()
            for model in self.models:
                self.assertEqual(model.objects.count(), 0)
        with tenant_atomic(self.context):
            self.app_role()
            for model, row, hidden in zip(self.models, local, foreign, strict=True):
                self.assertEqual(list(model.objects.values_list("pk", flat=True)), [row.pk])
                self.assertEqual(model.objects.filter(pk=hidden.pk).count(), 0)
            local[0].text = "Updated by runtime"
            local[0].save()
            with self.assertRaises(DatabaseError), transaction.atomic():
                ReplyTemplateTag.objects.bulk_create([
                    ReplyTemplateTag(organization=self.foreign, owner=self.foreign_member, name="Denied"),
                ])
        for model in self.models:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT relrowsecurity, relforcerowsecurity, pg_get_userbyid(relowner) "
                    "FROM pg_class WHERE relname = %s", [model._meta.db_table],
                )
                self.assertEqual(cursor.fetchone(), (True, True, "chatballs_schema"))
                cursor.execute("SELECT has_table_privilege('chatballs_runtime_platform', %s, 'SELECT')", [model._meta.db_table])
                self.assertFalse(cursor.fetchone()[0])

    def test_cross_tenant_and_library_relations_rejected_by_models_and_database(self):
        local = self.library(self.organization, self.employee)
        foreign = self.library(self.foreign, self.foreign_member)
        shared_category = ReplyTemplateCategory.objects.create(organization=self.organization, name="Shared")
        shared_tag = ReplyTemplateTag.objects.create(organization=self.organization, name="Shared")
        invalid = [
            ReplyTemplate(organization=self.organization, owner=self.foreign_member, title="Foreign owner", text="Text"),
            ReplyTemplate(organization=self.organization, owner=self.employee, category=foreign[1], title="Foreign category", text="Text"),
            ReplyTemplate(organization=self.organization, owner=self.employee, category=shared_category, title="Shared category", text="Text"),
            ReplyTemplateTagLink(organization=self.organization, template=local[0], tag=foreign[2]),
            ReplyTemplateTagLink(organization=self.organization, template=local[0], tag=shared_tag),
            ReplyTemplateManagementGrant(organization=self.organization, membership=self.foreign_member),
        ]
        for row in invalid:
            with self.subTest(model=type(row).__name__):
                with self.assertRaises(ValidationError):
                    row.save()
                with self.assertRaises(DatabaseError), transaction.atomic():
                    type(row).objects.bulk_create([row])
        with tenant_atomic(self.context):
            self.app_role()
            with self.assertRaisesMessage(DatabaseError, "library mismatch"), transaction.atomic():
                ReplyTemplate.objects.filter(pk=local[0].pk).update(category=shared_category)
            with self.assertRaisesMessage(DatabaseError, "library mismatch"), transaction.atomic():
                ReplyTemplateTagLink.objects.filter(pk=local[3].pk).update(tag=shared_tag)
            self.assertTrue(ReplyTemplateManagementGrant.objects.filter(pk=local[4].pk).exists())
            with self.assertRaises(DatabaseError), transaction.atomic():
                ReplyTemplateManagementGrant.objects.filter(pk=local[4].pk).update(membership_id=self.foreign_member.pk)
            for row in local[:3]:
                for changes in ({"owner_id": self.colleague.pk}, {"organization_id": self.foreign.pk}):
                    with self.assertRaisesMessage(DatabaseError, "ownership is immutable"), transaction.atomic():
                        type(row).objects.filter(pk=row.pk).update(**changes)

    def test_database_case_insensitive_uniqueness_is_partitioned_by_owner(self):
        for model, field, extra in (
            (ReplyTemplate, "title", {"text": "Text"}),
            (ReplyTemplateCategory, "name", {}), (ReplyTemplateTag, "name", {}),
        ):
            for owner in (None, self.employee, self.colleague):
                model.objects.create(organization=self.organization, owner=owner, **{field: "Name", **extra})
                with self.assertRaises(DatabaseError), transaction.atomic():
                    model.objects.bulk_create([model(
                        organization=self.organization, owner=owner, **{field: "NAME", **extra},
                    )])
