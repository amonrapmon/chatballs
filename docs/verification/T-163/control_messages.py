"""Owner-authorized control snapshots, ONLY in the disposable task database.

Run through manage.py shell with stdin after checking COMPOSE_PROJECT_NAME.
No provider, API or transport is replaced. This is NOT an AI/provider E2E check.
"""
import json
import os

from django.db import transaction

from chatballs.ai.models import AIAgent
from chatballs.ai.skill_templates.engine import render_template
from chatballs.ai.skill_templates.order_basis import order_basis
from chatballs.ai.skills_models import Skill
from chatballs.conversations.models import ConnectionIdentity, Contact, Conversation, Message
from chatballs.identity.models import OrganizationMembership
from chatballs.integrations.models import Integration
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.webchat.models import WebChatWidget

assert os.environ.get("T163_CONTROL_DATABASE") == "skaro-chatballs-t-163", "Task-only opt-in required"
membership = OrganizationMembership.objects.get(user__email="e.kuznetsova@atelie-nord.ru", role="ADMIN")
context = TenantContext.for_membership(membership)

with tenant_atomic(context), transaction.atomic():
    org = membership.organization
    agent = AIAgent.objects.get(organization=org, channel__code="site-support")
    assert not Integration.objects.filter(organization=org, name="T-163 control").exists(), "Already created"
    connection = Integration.objects.create(organization=org, channel=agent.channel, name="T-163 control",
                                           kind="MESSENGER", provider="WEB", status="OK", is_active=True)
    widget = WebChatWidget.objects.create(organization=org, integration=connection, code="t163-control",
                                         name="Web Chat", status="PUBLISHED", allowed_origins=["http://localhost:20005"])
    contact = Contact.objects.create(organization=org, name="Марина Волкова")
    identity = ConnectionIdentity.objects.create(connection=connection, contact=contact, external_user_id="t163-control")
    conversation = Conversation.objects.create(organization=org, channel=agent.channel, connection=connection,
                                              contact=contact, external_chat_id=identity.external_user_id,
                                              control_mode="PAUSED", expected_responder="CUSTOMER")
    basis = order_basis(language="ru")
    skill = Skill.objects.create(organization=org, name=basis["name"], description=basis["description"],
                                 instruction=basis["instruction"], templates=basis["templates"])

    def snapshot(template, data, *, representation="html", **extra):
        rendered = render_template(template, data, language="ru")
        return Message.objects.create(conversation=conversation, author_type="AI", text=rendered["text"],
                                      content_html=rendered["contentHtml"], presentation=rendered["presentation"],
                                      format_version=1, delivery_representation=representation,
                                      template_snapshot={"skillId": str(skill.public_id), "skillRevision": skill.revision,
                                                         "id": template["id"], "name": template["name"]}, **extra)

    card, status = basis["templates"]
    # Enough real persisted rows to exercise the ordinary history window/cursor.
    for index in range(52):
        snapshot(status, {"order_no": str(4400 + index), "status": "Принят"})
    Message.objects.create(conversation=conversation, author_type="CONTACT",
                           text="Здравствуйте! Что у меня в заказе 4512 и сколько к оплате?")
    Message.objects.create(conversation=conversation, author_type="AI", text="Здравствуйте, Марина! Вот состав заказа:")
    short = snapshot(card, card["examples"][0])
    eta = snapshot(status, status["examples"][0])
    long = snapshot(card, card["examples"][1])
    no_eta = snapshot(status, status["examples"][1])
    text = snapshot(card, card["examples"][0], representation="text")
    damaged = snapshot(status, status["examples"][1])
    damaged.presentation = {"formatVersion": 99, "srcDoc": "<script>bad()</script>"}
    damaged.save(update_fields=["presentation"])
    print(json.dumps({"organization": str(org.public_id), "conversation": conversation.pk,
                      "widgetKey": widget.public_key, "identity": identity.pk, "skill": str(skill.public_id),
                      "messages": {"short": short.pk, "eta": eta.pk, "long": long.pk, "noEta": no_eta.pk,
                                   "text": text.pk, "damaged": damaged.pk}}, ensure_ascii=False))
