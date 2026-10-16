"""Optional internal history hint, never a dependency of the saved content."""

from uuid import UUID

from chatballs.ai.skills_models import Skill


def add_template_updates(items, *, organization_id):
    references = {}
    for item in items:
        snapshot = item.get("template")
        if not isinstance(snapshot, dict) or item.get("deliveryRepresentation") != "html":
            continue
        try:
            identifier = UUID(str(snapshot.get("skillId")))
        except (ValueError, TypeError):
            continue
        if isinstance(snapshot.get("skillRevision"), int):
            references.setdefault(identifier, []).append(item)
    if not references:
        return
    # One query per history window, scoped explicitly as well as by tenant RLS.
    skills = Skill.objects.filter(organization_id=organization_id, public_id__in=references).values(
        "public_id", "revision", "updated_at", "templates",
    )
    for skill in skills:
        template_ids = {template.get("id") for template in skill["templates"]}
        for item in references[skill["public_id"]]:
            snapshot = item["template"]
            if skill["revision"] > snapshot["skillRevision"] and snapshot.get("id") in template_ids:
                item["templateUpdatedAt"] = skill["updated_at"].isoformat()
