import json
import sys
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from chatballs.support_portals.models import PortalArticle, SupportPortal
from chatballs.tenancy.context import TenantContext
from chatballs.tenancy.database import tenant_atomic
from chatballs.tenancy.ingress import support_portal_route
from chatballs.tenancy.lookup import load_organization


def checked_changes(portal: SupportPortal, plan: dict) -> list[PortalArticle]:
    if plan.get("portal") != portal.slug:
        raise CommandError("Portal slug differs from the curation plan")
    locale = plan.get("locale")
    order = plan.get("order")
    related = plan.get("related")
    if not isinstance(locale, str) or not isinstance(order, dict) or not isinstance(related, dict):
        raise CommandError("Invalid curation plan")
    articles = list(
        portal.articles.filter(
            locale=locale, status="PUBLISHED", published_revision__isnull=False
        ).select_related("category")
    )
    by_slug = {item.slug: item for item in articles}
    ordered = [slug for slugs in order.values() for slug in slugs]
    if (
        len(ordered) != len(by_slug)
        or len(set(ordered)) != len(ordered)
        or set(ordered) != set(by_slug)
        or set(related) != set(by_slug)
    ):
        raise CommandError("Plan must cover every published article exactly once")
    for category_slug, slugs in order.items():
        if not isinstance(slugs, list) or any(
            by_slug[slug].category.slug != category_slug for slug in slugs
        ):
            raise CommandError(f"Wrong article category in {category_slug}")
    for slug, targets in related.items():
        if (
            not isinstance(targets, list)
            or len(targets) > 5
            or len(set(targets)) != len(targets)
            or slug in targets
            or not set(targets) <= set(by_slug)
        ):
            raise CommandError(f"Invalid related articles for {slug}")
    changed = []
    for slugs in order.values():
        for position, slug in enumerate(slugs, start=1):
            article = by_slug[slug]
            target_ids = [by_slug[target].id for target in related[slug]]
            if article.sort_order != position or article.related_article_ids != target_ids:
                article.sort_order = position
                article.related_article_ids = target_ids
                changed.append(article)
    return changed


class Command(BaseCommand):
    help = "Validate or apply an editorial order and related articles to a public portal"

    def add_arguments(self, parser):
        parser.add_argument("--host", required=True)
        parser.add_argument("--file", required=True, help="JSON plan path or - for stdin")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        hostname = options["host"].strip().lower().rstrip(".")
        route = support_portal_route(hostname)
        organization = load_organization(route.organization_id) if route else None
        if organization is None:
            raise CommandError("Public portal host not found")
        source = sys.stdin.read() if options["file"] == "-" else Path(options["file"]).read_text(encoding="utf-8")
        try:
            plan = json.loads(source)
        except json.JSONDecodeError as error:
            raise CommandError("Invalid JSON plan") from error
        context = TenantContext.for_resource(organization)
        with tenant_atomic(context):
            portal = SupportPortal.objects.filter(
                id=route.resource_id,
                organization=organization,
                status="PUBLISHED",
            ).first()
            if portal is None:
                raise CommandError("Published portal not found")
            changed = checked_changes(portal, plan)
            if options["apply"] and changed:
                PortalArticle.objects.bulk_update(
                    changed, ["sort_order", "related_article_ids"]
                )
        action = "Updated" if options["apply"] else "Would update"
        self.stdout.write(f"{action} {len(changed)} articles")
