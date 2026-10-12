"""Explicit control area, independent of ordinary group membership (ADR-0033)."""

from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class EmployeeGroupSupervision(TenantRelationModel):
    tenant_relation_fields = ("group", "employee")
    group = models.ForeignKey(
        "identity.EmployeeGroup", on_delete=models.CASCADE, related_name="supervision_links"
    )
    employee = models.ForeignKey(
        "identity.OrganizationMembership",
        on_delete=models.CASCADE,
        related_name="supervision_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["group", "employee"], name="uniq_employee_group_supervision"
            )
        ]


def supervised_groups_payload(membership) -> list[dict[str, object]]:
    links = membership.supervision_links.all()
    if "supervision_links" not in getattr(membership, "_prefetched_objects_cache", {}):
        links = links.select_related("group")
    groups = [
        {"id": link.group_id, "name": link.group.name}
        for link in links
    ]
    groups.sort(key=lambda item: (str(item["name"]), item["id"]))
    return groups
