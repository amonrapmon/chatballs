from django.core.exceptions import ValidationError

from chatballs.i18n import t
from chatballs.support_portals.models import PortalArticle
from chatballs.support_portals.statuses import ArticleStatus


def apply_article_curation(article: PortalArticle, data: dict) -> None:
    if "sortOrder" in data:
        article.sort_order = int(data["sortOrder"])
    if "relatedArticleIds" not in data:
        return
    related_ids = data["relatedArticleIds"]
    if (
        not isinstance(related_ids, list)
        or len(related_ids) > 5
        or any(type(item) is not int for item in related_ids)
        or len(set(related_ids)) != len(related_ids)
        or article.id in related_ids
    ):
        raise ValidationError({"relatedArticleIds": t("portals.invalid_article_data")})
    valid_count = PortalArticle.objects.filter(
        id__in=related_ids,
        portal=article.portal,
        locale=article.locale,
        status=ArticleStatus.PUBLISHED,
        published_revision__isnull=False,
    ).count()
    if valid_count != len(related_ids):
        raise ValidationError({"relatedArticleIds": t("portals.invalid_article_data")})
    article.related_article_ids = related_ids
