"""API правил и журнала: кто управляет, что проверяет сервер и кому виден журнал."""

from unittest import mock

from django.test import TestCase

from chatballs.channels.models import Channel
from chatballs.conversations.models import Contact, Conversation
from chatballs.conversations.rules import executor
from chatballs.conversations.rules.models import (
    HandlingRule,
    HandlingRuleKind,
    RuleExecution,
    RuleExecutionReason,
)
from chatballs.conversations.rules.rule_test_base import RuleScene
from chatballs.conversations.rules.settings import rule_for
from chatballs.events.services import MAX_OUTBOX_ATTEMPTS
from chatballs.i18n import t
from chatballs.identity.group_models import EmployeeGroup
from chatballs.identity.models import (
    EmployeeRole,
    HumanUser,
    Organization,
    OrganizationMembership,
)
from chatballs.testing import TenantAPIClient

RULES = "/api/v1/conversations/rules/"
JOURNAL = "/api/v1/conversations/rule-executions/"
CONFIRMATION = HandlingRuleKind.RECEIPT_CONFIRMATION
NOTICE = HandlingRuleKind.WAIT_EXCEEDED_NOTICE
RETURN = HandlingRuleKind.ASSIGNMENT_RETURN


class RuleApiScene(RuleScene):
    def setUp(self) -> None:
        super().setUp()
        self.admin = self.employee("admin", EmployeeRole.ADMIN)

    def client_for(self, membership: OrganizationMembership) -> TenantAPIClient:
        client = TenantAPIClient()
        client.force_authenticate(membership.user)
        return client

    def patch(self, kind: str, data: dict, membership: OrganizationMembership | None = None):
        return self.client_for(membership or self.owner).patch(
            f"{RULES}{kind}/", data, format="json"
        )


class RuleSettingsApiTests(RuleApiScene, TestCase):
    slug = "rule-api"

    def test_managers_read_every_rule_with_what_it_accepts(self) -> None:
        response = self.client_for(self.admin).get(RULES)
        self.assertEqual(response.status_code, 200)
        items = {item["kind"]: item for item in response.json()["items"]}
        self.assertEqual(set(items), set(HandlingRuleKind.values))
        self.assertEqual(
            {kind: item["enabled"] for kind, item in items.items()},
            {CONFIRMATION: False, NOTICE: False, "REPLY_REMINDER": False, RETURN: True},
        )
        self.assertEqual(
            items[CONFIRMATION]["catalog"],
            {
                "conditions": ["channelIds"], "recipients": [], "requiresText": True,
                "maxDelayMinutes": 1440, "maxTextLength": 1000, "deadlinePlaceholder": "{срок}",
            },
        )
        self.assertEqual(
            (items[NOTICE]["catalog"]["conditions"], items[NOTICE]["catalog"]["recipients"]),
            (["availableOnly", "channelIds"], ["CONVERSATION_GROUP", "GROUP_SUPERVISORS", "MANAGEMENT"]),
        )
        self.assertEqual(
            items["REPLY_REMINDER"]["catalog"]["recipients"],
            ["ASSIGNEE", "GROUP_SUPERVISORS", "MANAGEMENT"],
        )
        for reader in (self.operator, self.supervisor("lead", self.group)):
            with self.subTest(role=reader.role):
                self.assertEqual(self.client_for(reader).get(RULES).status_code, 403)

    def test_owner_and_admin_change_each_rule_independently(self) -> None:
        response = self.patch(
            CONFIRMATION,
            {"enabled": True, "delayMinutes": 20, "text": "Received, {срок}",
             "conditions": {"channelIds": [self.channel.pk]}},
        )
        self.assertEqual(response.status_code, 200, response.content)
        rule = response.json()["rule"]
        self.assertEqual(
            (rule["enabled"], rule["version"], rule["delayMinutes"], rule["text"],
             rule["conditions"], rule["updatedBy"]),
            (True, 2, 20, "Received, {срок}", {"channelIds": [self.channel.pk]},
             self.owner.user.email),
        )
        response = self.patch(
            NOTICE, {"enabled": True, "delayMinutes": 9, "recipients": ["MANAGEMENT"]}, self.admin
        )
        self.assertEqual((response.status_code, response.json()["rule"]["version"]), (200, 2))
        # Соседние правила своего состояния и версии не меняют.
        listed = self.client_for(self.owner).get(RULES).json()["items"]
        self.assertEqual(
            {(item["kind"], item["enabled"], item["version"]) for item in listed},
            {(CONFIRMATION, True, 2), (NOTICE, True, 2), ("REPLY_REMINDER", False, 1),
             (RETURN, True, 1)},
        )
        self.assertEqual(self.patch(NOTICE, {"enabled": False}).json()["rule"]["version"], 3)
        self.assertTrue(rule_for(self.organization.pk, CONFIRMATION).enabled)

    def test_server_rejects_what_is_outside_the_catalog_or_the_organization(self) -> None:
        foreign = Channel.objects.create(
            organization=Organization.objects.create(name="Other", slug="other-rule-api"),
            code="other", name="Other",
        )
        cases = (
            (NOTICE, {"conditions": {"channelIds": [foreign.pk]}}),
            (NOTICE, {"conditions": {"sql": "1 = 1"}}),
            (NOTICE, {"recipients": ["EVERYONE"]}),
            (NOTICE, {"recipients": [self.owner.user_id]}),
            (NOTICE, {"recipients": ["ASSIGNEE"]}),
            (NOTICE, {"enabled": True, "delayMinutes": 5}),
            (NOTICE, {"script": "import os"}),
            (NOTICE, ["enabled"]),
            (CONFIRMATION, {"enabled": True, "delayMinutes": 5}),
            (CONFIRMATION, {"recipients": ["MANAGEMENT"]}),
            (CONFIRMATION, {"delayMinutes": 0}),
        )
        for kind, data in cases:
            with self.subTest(kind=kind, data=data):
                self.assertEqual(self.patch(kind, data).status_code, 400)
        self.assertEqual(self.patch("EXEC_PYTHON", {"enabled": True}).status_code, 404)
        # Отклонённый запрос ничего не включил и версию не сдвинул.
        self.assertFalse(
            HandlingRule.objects.filter(organization=self.organization)
            .exclude(kind=RETURN).exclude(enabled=False, version=1).exists()
        )

    def test_only_owner_and_admin_change_rules(self) -> None:
        for editor in (self.operator, self.supervisor("lead", self.group)):
            with self.subTest(role=editor.role):
                self.assertEqual(self.patch(RETURN, {"enabled": False}, editor).status_code, 403)
        self.assertTrue(rule_for(self.organization.pk, RETURN).enabled)


class RuleJournalApiTests(RuleApiScene, TestCase):
    slug = "rule-journal"

    def setUp(self) -> None:
        super().setUp()
        self.sales = EmployeeGroup.objects.create(organization=self.organization, name="Sales")
        self.lead = self.supervisor("lead", self.group)
        self.sales_lead = self.supervisor("sales-lead", self.sales)
        self.support_execution = self.assign(self.operator)
        self.sales_conversation = Conversation.objects.create(
            organization=self.organization, channel=self.channel, connection=self.connection,
            group=self.sales, contact=Contact.objects.create(organization=self.organization),
            control_mode="PAUSED", waiting_since=self.conversation.waiting_since,
        )
        self.sales_execution = self.assign(self.colleague, self.sales_conversation)

    def journal(self, membership: OrganizationMembership, **params):
        return self.client_for(membership).get(JOURNAL, params)

    def ids(self, response) -> list[int]:
        return [item["id"] for item in response.json()["items"]]

    def test_journal_is_paginated_and_limited_to_the_allowed_area(self) -> None:
        response = self.journal(self.owner, pageSize=1)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            (body["total"], body["pageCount"], body["pageSize"], len(body["items"])), (2, 2, 1, 1)
        )
        second = self.journal(self.admin, pageSize=1, page=2)
        self.assertEqual(
            set(self.ids(response) + self.ids(second)),
            {self.support_execution.pk, self.sales_execution.pk},
        )
        # Супервизор видит записи обращений только своей области контроля.
        self.assertEqual(self.ids(self.journal(self.lead)), [self.support_execution.pk])
        self.assertEqual(self.ids(self.journal(self.sales_lead)), [self.sales_execution.pk])
        self.assertEqual(
            self.ids(self.journal(self.lead, conversationId=self.sales_conversation.pk)), []
        )
        # Обращение перевели в другую группу — журнал идёт за ним.
        Conversation.objects.filter(pk=self.conversation.pk).update(group=self.sales)
        self.assertEqual(self.ids(self.journal(self.lead)), [])
        self.assertEqual(self.journal(self.sales_lead).json()["total"], 2)
        for reader in (self.operator, self.supervisor("no-area")):
            with self.subTest(role=reader.role):
                self.assertEqual(self.journal(reader).status_code, 403)

    def test_other_organization_sees_nothing(self) -> None:
        other = Organization.objects.create(name="Other", slug="other-journal")
        stranger = OrganizationMembership.objects.create(
            user=HumanUser.objects.create_user(email="owner@other-journal.test"),
            organization=other, role=EmployeeRole.OWNER,
        )
        response = self.journal(stranger)
        self.assertEqual((response.status_code, response.json()["total"]), (200, 0))
        self.assertEqual(
            self.journal(stranger, conversationId=self.conversation.pk).json()["items"], []
        )

    def test_record_shows_the_rule_the_source_and_a_safe_reason(self) -> None:
        failing = executor.ActionHandler(
            stale_reason=executor.ACTIONS["RETURN_TO_QUEUE"].stale_reason,
            perform=mock.Mock(side_effect=RuntimeError("token=secret-value at 10.0.0.5")),
        )
        with mock.patch.dict(executor.ACTIONS, {"RETURN_TO_QUEUE": failing}):
            for _ in range(MAX_OUTBOX_ATTEMPTS):
                with self.assertRaises(RuntimeError):
                    self.deliver(self.support_execution)
        self.deliver(self.sales_execution)

        response = self.journal(self.owner)
        self.assertNotIn("secret-value", response.content.decode())
        items = {item["id"]: item for item in response.json()["items"]}
        failed = items[self.support_execution.pk]
        fact = self.support_execution.source_event
        self.assertEqual(
            (failed["rule"], failed["action"], failed["conversationId"], failed["status"],
             failed["reason"], failed["reasonLabel"], failed["attempts"]),
            ({"kind": RETURN, "version": 1}, "RETURN_TO_QUEUE", self.conversation.pk, "FAILED",
             "execution_error", "Действие не удалось выполнить", MAX_OUTBOX_ATTEMPTS),
        )
        self.assertEqual(
            failed["sourceEvent"],
            {"id": fact.pk, "type": "ASSIGNED", "occurredAt": fact.occurred_at.isoformat()},
        )
        self.assertEqual(
            failed["scheduledFor"], self.support_execution.scheduled_for.isoformat()
        )
        self.assertIsNotNone(failed["finishedAt"])
        done = items[self.sales_execution.pk]
        self.sales_execution.refresh_from_db()
        self.assertEqual(
            (done["status"], done["reason"], done["reasonLabel"], done["messageId"],
             done["notificationId"]),
            ("EXECUTED", "", "", self.sales_execution.message_id,
             self.sales_execution.notification_id),
        )
        self.assertEqual(self.ids(self.journal(self.owner, status="FAILED")), [failed["id"]])
        self.assertEqual(self.journal(self.owner, kind=RETURN).json()["total"], 2)
        self.assertEqual(self.journal(self.owner, kind=NOTICE).json()["total"], 0)
        for params in ({"status": "DONE"}, {"kind": "ANY"}, {"conversationId": "1 OR 1=1"}):
            with self.subTest(params=params):
                self.assertEqual(self.journal(self.owner, **params).status_code, 400)

    def test_every_reason_code_has_a_label_in_both_languages(self) -> None:
        for language in ("ru", "en"):
            for reason in RuleExecutionReason.values:
                with self.subTest(language=language, reason=reason):
                    key = f"rules.reason_{reason}"
                    self.assertNotEqual(t(key, language=language), key)

    def test_personal_recipients_are_named_in_the_record(self) -> None:
        self.patch(NOTICE, {"enabled": True, "delayMinutes": 3, "recipients": ["GROUP_SUPERVISORS"]})
        conversation = self.receive("first")
        execution = self.executions(conversation).get(action="NOTIFY_WAIT_EXCEEDED")
        self.deliver(execution)
        record = self.journal(self.owner, kind=NOTICE).json()["items"][0]
        self.assertEqual(
            record["recipients"], [{"userId": self.lead.user_id, "name": self.lead.user.email}]
        )

    def test_disabling_reaches_pending_work_and_leaves_past_effects(self) -> None:
        self.deliver(self.sales_execution)
        self.sales_execution.refresh_from_db()
        message_id, notification_id = (
            self.sales_execution.message_id, self.sales_execution.notification_id
        )

        self.assertEqual(self.patch(RETURN, {"enabled": False}).status_code, 200)
        items = {item["id"]: item for item in self.journal(self.owner).json()["items"]}
        pending = items[self.support_execution.pk]
        self.assertEqual(
            (pending["status"], pending["reason"], pending["reasonLabel"]),
            ("SKIPPED", "rule_disabled", "Правило выключено"),
        )
        self.assertIsNotNone(pending["finishedAt"])
        # Выключенное правило ожидающую работу не выполняет.
        self.deliver(self.support_execution)
        self.conversation.refresh_from_db()
        self.assertEqual(self.conversation.assigned_operator_id, self.operator.user_id)
        # Уже сделанное остаётся: запись журнала, сообщение ленты и уведомление.
        done = items[self.sales_execution.pk]
        self.assertEqual(
            (done["status"], done["messageId"], done["notificationId"]),
            ("EXECUTED", message_id, notification_id),
        )
        self.assertTrue(self.sales_conversation.messages.filter(pk=message_id).exists())
        self.sales_conversation.refresh_from_db()
        self.assertIsNone(self.sales_conversation.assigned_operator_id)
        self.assertEqual(RuleExecution.objects.filter(organization=self.organization).count(), 2)
