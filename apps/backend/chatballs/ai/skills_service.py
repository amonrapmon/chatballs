"""Atomic library writes. No changes to prompts, turns or messages."""

import json
import uuid

from django.utils.crypto import salted_hmac

from chatballs.ai.models import AIAgent
from chatballs.ai.skills_models import AgentSkill, Skill, SkillRequest
from chatballs.ai.skills_queries import load, require_manager
from chatballs.ai.skills_validation import SkillError, configuration, expected_revision
from chatballs.identity.audit import record_audit_event
from chatballs.identity.models import Organization
from chatballs.tenancy.database import tenant_atomic


def _lock_organization(context):
    require_manager(context)
    # One ordering for all writes also serializes request-key retries. No lock
    # on another tenant, and no check-then-insert race for new configuration.
    Organization.objects.select_for_update().get(pk=context.organization_id)


def _audit(context, action, skill, **payload):
    record_audit_event(
        action=f"ai.skill_{action}", actor=context.actor_user,
        organization=context.organization, object_type="Skill",
        object_id=str(skill.public_id), payload={"revision": skill.revision, **payload},
    )


def _bump(context, skill):
    skill.revision += 1
    skill.updated_by = context.actor_user
    skill.save()


def _check_revision(skill, value):
    if skill.revision != expected_revision(value):
        raise SkillError("revision_conflict", status=409)


def _request(context, key, operation, raw):
    try:
        key = uuid.UUID(str(key))
    except (ValueError, TypeError, AttributeError):
        raise SkillError("invalid_request_key", field="requestId") from None
    fingerprint = salted_hmac(
        "skill-request", json.dumps([operation, raw], sort_keys=True, ensure_ascii=True),
        algorithm="sha256",
    ).hexdigest()
    receipt = SkillRequest.objects.filter(organization_id=context.organization_id, key=key).first()
    if receipt and receipt.fingerprint != fingerprint:
        raise SkillError("request_conflict", status=409)
    return key, fingerprint, receipt


def save_configuration(*, context, raw, request_id, public_id=None, revision=None):
    require_manager(context)
    values = configuration(raw)
    if public_id is not None:
        expected_revision(revision)
    with tenant_atomic(context):
        _lock_organization(context)
        key, fingerprint, receipt = _request(
            context, request_id, ["save", str(public_id), revision], raw
        )
        if receipt:
            current = load(context, receipt.skill_public_id)
            if public_id is not None and current.revision != receipt.result_revision:
                raise SkillError("revision_conflict", status=409)
            return current, False
        if public_id is None:
            skill = Skill.objects.create(
                organization=context.organization, created_by=context.actor_user,
                updated_by=context.actor_user, **values,
            )
            _audit(context, "created", skill)
        else:
            skill = load(context, public_id, lock=True)
            _check_revision(skill, revision)
            for field, value in values.items():
                setattr(skill, field, value)
            _bump(context, skill)
            _audit(context, "updated", skill)
        SkillRequest.objects.create(
            organization=context.organization, key=key, fingerprint=fingerprint,
            skill_public_id=skill.public_id, result_revision=skill.revision,
        )
        return skill, public_id is None


def delete_configuration(*, context, public_id, revision):
    with tenant_atomic(context):
        _lock_organization(context)
        skill = load(context, public_id, lock=True)
        _check_revision(skill, revision)
        agent_ids = list(skill.assignments.values_list("agent__channel_id", flat=True))
        _audit(context, "deleted", skill, agentIds=agent_ids)
        skill.delete()  # Only current config and assignments; audit/receipts stay.


def set_assignment(*, context, public_id, agent_id, enabled, revision):
    with tenant_atomic(context):
        _lock_organization(context)
        skill = load(context, public_id, lock=True)
        agent = AIAgent.objects.select_for_update().filter(
            organization_id=context.organization_id, channel_id=agent_id,
        ).first()
        if agent is None:
            raise SkillError("agent_not_found", status=404)
        expected_revision(revision)
        rows = AgentSkill.objects.filter(skill=skill, agent=agent)
        if rows.exists() == enabled:
            return skill
        _check_revision(skill, revision)
        if enabled:
            AgentSkill.objects.create(organization=context.organization, skill=skill, agent=agent)
        else:
            rows.delete()
        _bump(context, skill)
        _audit(context, "attached" if enabled else "detached", skill, agentId=agent_id)
        return skill
