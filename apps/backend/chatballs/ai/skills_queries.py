"""Library access and metadata; administrative APIs only."""

from django.db.models import Prefetch

from chatballs.ai.skills_models import AgentSkill, Skill
from chatballs.ai.skills_validation import SkillError
from chatballs.identity.policy import has_capability_any_scope


def require_manager(context):
    membership = context.membership
    if (
        membership is None
        or membership.organization_id != context.organization_id
        or context.actor_user is None
        or membership.user_id != context.actor_user.pk
        or not has_capability_any_scope(membership, "ai.manage")
    ):
        raise SkillError("forbidden", status=403)


def library(context):
    require_manager(context)
    return Skill.objects.filter(organization_id=context.organization_id).select_related(
        "created_by", "updated_by"
    ).prefetch_related(Prefetch(
        "assignments", queryset=AgentSkill.objects.select_related("agent__channel").order_by("agent__channel__name", "agent_id")
    ))


def load(context, public_id, *, lock=False):
    require_manager(context)
    rows = Skill.objects.filter(organization_id=context.organization_id, public_id=public_id)
    if lock:
        rows = rows.select_for_update()
    skill = rows.first()
    if skill is None:
        raise SkillError("not_found", status=404)
    return skill


def skill_payload(skill, *, full=False):
    def author(user):
        return {"id": user.pk, "name": user.full_name} if user else None

    agents = [
        {"id": row.agent.channel_id, "aiAgentId": row.agent_id, "name": row.agent.channel.name}
        for row in skill.assignments.all()
    ]
    result = {
        "id": str(skill.public_id), "name": skill.name, "description": skill.description,
        "revision": skill.revision, "templates": [], "templateCount": 0,
        "agents": agents, "agentCount": len(agents),
        "createdBy": author(skill.created_by), "updatedBy": author(skill.updated_by),
        "createdAt": skill.created_at.isoformat(), "updatedAt": skill.updated_at.isoformat(),
    }
    if full:
        result["instruction"] = skill.instruction
    return result
