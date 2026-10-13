from django.utils import timezone
from rest_framework.test import APIClient

from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import HumanUser, OrganizationMembership
from chatballs.identity.supervision_models import EmployeeGroupSupervision
from chatballs.ratings.credentials import credential_for
from chatballs.ratings.models import RatingRequest
from chatballs.ratings.results import protected_payload, results_for_context, scale_groups
from chatballs.ratings.test_support import RatingTestBase
from chatballs.ratings.web_delivery import deliver_due_requests, session_requests
from chatballs.tenancy.context import TenantContext


class RatingResultsTests(RatingTestBase):
    def submit(self, value=5):
        target = self.scheduled()
        deliver_due_requests(self.context)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(target)}")
        self.assertEqual(client.post("/api/v1/ratings/", {"value": value}, format="json").status_code, 201)
        return target

    def test_attribution_and_grouping_count_multi_responder_rating_once(self):
        another = HumanUser.objects.create_user(email="second-responder@ratings.test")
        OrganizationMembership.objects.create(organization=self.organization, user=another, role="EMPLOYEE")
        self.row(event_type="PUBLIC_REPLY").save()
        self.row(event_type="PUBLIC_REPLY", initiated_by_id=another.pk).save()
        target = self.submit()
        self.assertEqual(target.responder_ids, sorted([self.user.pk, another.pk]))
        results = results_for_context(self.context)
        self.assertEqual(scale_groups(results)[0]["count"], 1)
        self.assertEqual(protected_payload(results.get())["responderIds"], target.responder_ids)
        self.assertEqual(session_requests(self.session), [])
        self.policy.scale[0]["label"] = "Different scale label"
        self.policy.save()
        event = self.row(event_type="CLOSED")
        event.save()
        second = RatingRequest.objects.get(completion=event)
        deliver_due_requests(self.context)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {credential_for(second)}")
        self.assertEqual(client.post("/api/v1/ratings/", {"value": 4}, format="json").status_code, 201)
        groups = scale_groups(results_for_context(self.context))
        self.assertEqual(len(groups), 2)
        self.assertEqual([group["count"] for group in groups], [1, 1])
        self.assertTrue(all("average" not in group for group in groups))

    def test_http_management_access_is_current_and_operator_is_denied(self):
        self.submit()
        operator = HumanUser.objects.create_user(email="rating-operator@ratings.test")
        membership = OrganizationMembership.objects.create(
            organization=self.organization, user=operator, role="SUPERVISOR",
        )
        link = EmployeeGroupSupervision.objects.create(
            organization=self.organization, employee=membership, group=self.group,
        )
        client = APIClient()
        prefix = f"/api/v1/organizations/{self.organization.public_id}/ratings/"
        client.force_login(operator)
        self.assertEqual(client.get(prefix + "results/").data["count"], 1)
        card = prefix + f"conversations/{self.conversation.pk}/"
        self.assertEqual(len(client.get(card).data["results"]), 1)
        self.assertEqual(client.get(prefix + f"conversations/{self.foreign_conversation.pk}/").status_code, 404)
        link.delete()
        self.assertEqual(client.get(prefix + "results/").data["count"], 0)
        self.assertEqual(client.get(card).status_code, 404)
        # Ordinary membership or responsibility does not grant report access.
        membership.role = "EMPLOYEE"
        membership.save()
        self.assertEqual(client.get(prefix + "results/").status_code, 403)
        self.assertEqual(client.get(card).status_code, 403)
        self.assertEqual(client.get(prefix + "settings/").status_code, 403)
        client.force_login(self.user)
        self.assertEqual(client.get(prefix + "results/").data["count"], 1)
        self.member.role = "ADMIN"
        self.member.save()
        self.assertEqual(client.get(prefix + "results/").data["count"], 1)

    def test_current_group_scope_filters_totals_staff_and_tenant(self):
        self.row(event_type="PUBLIC_REPLY").save()
        self.submit()
        user = HumanUser.objects.create_user(email="rating-supervisor@ratings.test")
        membership = OrganizationMembership.objects.create(organization=self.organization, user=user, role="SUPERVISOR")
        EmployeeGroupSupervision.objects.create(organization=self.organization, employee=membership, group=self.group)
        context = TenantContext.for_membership(membership)
        self.assertEqual(results_for_context(context).count(), 1)
        client = APIClient()
        client.force_login(user)
        path = f"/api/v1/organizations/{self.organization.public_id}/ratings/results/"
        self.assertEqual(client.get(path, {"responderId": self.user.pk}).data["count"], 1)
        self.assertEqual(client.get(path, {"responderId": self.foreign_user.pk}).data["count"], 0)
        self.assertEqual(client.get(path, {"groupId": self.foreign_group.pk}).data["count"], 0)
        self.assertEqual(client.get(path, {"limit": "bad"}).status_code, 400)
        another_group = EmployeeGroup.objects.create(organization=self.organization, name="Other current group")
        self.conversation.group = another_group
        self.conversation.save()
        self.assertEqual(client.get(path).data["count"], 0)
        self.assertEqual(results_for_context(self.foreign_context()).count(), 0)
        membership.blocked_at = timezone.now()
        membership.save()
        self.assertEqual(client.get(path).status_code, 404)

    def foreign_context(self):
        return TenantContext.for_membership(self.foreign_member)
