"""Dry-run-first reconciliation for rolled-back staged Connector files."""
from __future__ import annotations

import json
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from chatballs.conversations.connector_media_gc import reconcile_connector_media_orphans
from chatballs.identity.models import Organization


class Command(BaseCommand):
    help = "Inspect orphaned staged Connector attachments; deletion needs --delete."

    def add_arguments(self, parser):
        parser.add_argument("--organization-id", type=int, required=True)
        parser.add_argument("--older-than-hours", type=int, default=24)
        parser.add_argument("--max-files", type=int, default=1000)
        parser.add_argument("--delete", action="store_true", default=False)

    def handle(self, *args, **options):
        if options["older_than_hours"] < 1 or options["max_files"] < 1:
            raise CommandError("age and max-files must be positive")
        organization = Organization.objects.filter(pk=options["organization_id"]).first()
        if organization is None:
            raise CommandError("Organization not found")
        try:
            result = reconcile_connector_media_orphans(
                organization=organization,
                delete=options["delete"],
                min_age=timedelta(hours=options["older_than_hours"]),
                max_files=options["max_files"],
            )
        except (OSError, ValueError) as error:
            raise CommandError("Connector media reconciliation stopped") from error
        self.stdout.write(json.dumps({
            "mode": "delete" if options["delete"] else "dry_run",
            "organizationId": organization.id,
            **result,
        }, sort_keys=True))
        if result["truncated"]:
            self.stderr.write(self.style.WARNING("Scan limit reached; rerun with a higher cap."))
