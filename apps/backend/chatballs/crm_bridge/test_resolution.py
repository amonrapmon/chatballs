"""Context-specific CRM links, branch selection and visibility."""

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.crm_bridge.models import CRMCompany, CRMConnectionBinding, CRMOrganizationConfig
from chatballs.crm_bridge.resolution import links_for_contact, links_for_conversation
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import EmployeeRole, HumanUser, Organization, OrganizationMembership
from chatballs.integrations.models import Integration, IntegrationKind, IntegrationProvider
from chatballs.tenancy.context import TenantContext


class CRMBridgeResolutionTests(TestCase):
    def setUp(self):
        self.org = Organization.objects.create(name="Branch studio", slug="crm-links")
        self.owner = HumanUser.objects.create_user(email="crm-links-owner@example.test")
        self.worker = HumanUser.objects.create_user(email="crm-links-worker@example.test")
        self.owner_membership = OrganizationMembership.objects.create(
            organization=self.org, user=self.owner,
            role=EmployeeRole.OWNER, position_title="Owner",
        )
        self.worker_membership = OrganizationMembership.objects.create(
            organization=self.org, user=self.worker,
            role=EmployeeRole.EMPLOYEE, position_title="Operator",
        )
        self.owner_context = TenantContext.for_membership(self.owner_membership)
        self.worker_context = TenantContext.for_membership(self.worker_membership)
        self.group = EmployeeGroup.objects.create(organization=self.org, name="Private")
        self.channel = Channel.objects.create(
            organization=self.org, code="support", name="Support",
        )
        self.telegram = Integration.objects.create(
            organization=self.org, kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.TELEGRAM, name="TG",
        )
        self.max = Integration.objects.create(
            organization=self.org, kind=IntegrationKind.MESSENGER,
            provider=IntegrationProvider.MAX, name="MAX",
        )
        self.contact = Contact.objects.create(
            organization=self.org, name="Client", phone="+7 (916) 254-52-43",
        )
        self.public_conversation = Conversation.objects.create(
            organization=self.org, channel=self.channel,
            connection=self.telegram, contact=self.contact,
        )
        self.private_conversation = Conversation.objects.create(
            organization=self.org, channel=self.channel,
            connection=self.max, contact=self.contact,
            group=self.group,
        )
        self.config = CRMOrganizationConfig.objects.create(
            organization=self.org, provider="YCLIENTS", last_active_provider="YCLIENTS",
        )
        self.first = CRMCompany.objects.create(
            organization=self.org, name="West", external_company_id="111", is_primary=True,
        )
        self.second = CRMCompany.objects.create(
            organization=self.org, name="East", external_company_id="222",
        )
        self.binding_a = CRMConnectionBinding.objects.create(
            organization=self.org, integration=self.telegram, crm_company=self.first,
        )
        self.binding_b = CRMConnectionBinding.objects.create(
            organization=self.org, integration=self.max, crm_company=self.second,
        )

    def test_conversation_uses_its_integration_not_primary_company(self):
        answer = links_for_conversation(
            context=self.owner_context, conversation_id=self.private_conversation.id
        )
        self.assertEqual(answer["state"], "ok")
        self.assertEqual(len(answer["links"]), 1)
        self.assertEqual(answer["links"][0]["companyName"], "East")
        self.assertIn("/clients/222/base?", answer["links"][0]["url"])

    def test_shared_contact_shows_two_named_companies(self):
        answer = links_for_contact(context=self.owner_context, contact_id=self.contact.id)
        self.assertEqual(answer["state"], "multiple_companies")
        self.assertEqual([link["companyName"] for link in answer["links"]], ["East", "West"])

    def test_worker_never_sees_inaccessible_private_branch(self):
        answer = links_for_contact(context=self.worker_context, contact_id=self.contact.id)
        self.assertEqual(answer["state"], "ok")
        self.assertEqual([link["companyName"] for link in answer["links"]], ["West"])
        with self.assertRaises(Conversation.DoesNotExist):
            links_for_conversation(
                context=self.worker_context, conversation_id=self.private_conversation.id
            )

    def test_unbound_multibranch_does_not_guess_primary(self):
        self.binding_b.delete()
        answer = links_for_conversation(
            context=self.owner_context, conversation_id=self.private_conversation.id,
        )
        self.assertEqual(answer, {"state": "ambiguous_company", "links": []})
        contacts = links_for_contact(context=self.owner_context, contact_id=self.contact.id)
        self.assertEqual(contacts["state"], "partial")
        self.assertEqual([link["companyName"] for link in contacts["links"]], ["West"])

    def test_single_active_company_is_unambiguous_fallback(self):
        self.binding_b.delete()
        self.second.delete()
        answer = links_for_conversation(
            context=self.owner_context, conversation_id=self.private_conversation.id,
        )
        self.assertEqual(answer["state"], "ok")
        self.assertEqual(answer["links"][0]["companyName"], "West")

    def test_no_phone_or_disabled_crm_never_yields_url(self):
        self.contact.phone = ""
        self.contact.save(update_fields=["phone"])
        answer = links_for_conversation(
            context=self.owner_context, conversation_id=self.public_conversation.id,
        )
        self.assertEqual(answer["state"], "no_phone")
        self.contact.phone = "79162545243"
        self.contact.save(update_fields=["phone"])
        self.config.provider = "NONE"
        self.config.save(update_fields=["provider"])
        answer = links_for_contact(context=self.owner_context, contact_id=self.contact.id)
        self.assertEqual(answer, {"state": "disabled", "links": []})
