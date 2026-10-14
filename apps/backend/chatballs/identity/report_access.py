"""Effective team-report actions, independent of ordinary conversation access."""

from chatballs.identity.models import EmployeeRole


def report_actions(actor, supervised_groups=None):
    if actor.role in {EmployeeRole.OWNER, EmployeeRole.ADMIN}:
        return ["reports.view", "reports.export"]
    if actor.role == EmployeeRole.SUPERVISOR:
        controlled = supervised_groups if supervised_groups is not None else actor.supervision_links.exists()
        if controlled:
            return ["reports.view", "reports.export"]
    return []
