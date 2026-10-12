"""Reply libraries are owned by an organization or one of its memberships."""

from django.core.exceptions import ValidationError
from django.db import models

from chatballs.tenancy.models import TenantRelationModel


class ScopedTemplateModel(TenantRelationModel):
    tenant_relation_fields = ("owner",)
    owner = models.ForeignKey(
        "identity.OrganizationMembership", on_delete=models.CASCADE,
        null=True, blank=True, related_name="+",
    )

    class Meta:
        abstract = True

    @property
    def scope(self):
        return "PERSONAL" if self.owner_id is not None else "SHARED"

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self._meta.model_name}:{self.organization_id}/{self.pk}"


def scoped_name_constraints(field, prefix):
    return [
        models.UniqueConstraint(
            models.functions.Lower(field), "organization",
            condition=models.Q(owner__isnull=True), name=f"{prefix}_shared_ci",
        ),
        models.UniqueConstraint(
            models.functions.Lower(field), "organization", "owner",
            condition=models.Q(owner__isnull=False), name=f"{prefix}_personal_ci",
        ),
    ]


class ReplyTemplateCategory(ScopedTemplateModel):
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name", "id"]
        constraints = scoped_name_constraints("name", "template_category")


class ReplyTemplateTag(ScopedTemplateModel):
    name = models.CharField(max_length=120)

    class Meta:
        ordering = ["name", "id"]
        constraints = scoped_name_constraints("name", "template_tag")


class ReplyTemplate(ScopedTemplateModel):
    tenant_relation_fields = ("owner", "category")
    organization = models.ForeignKey(
        "identity.Organization", on_delete=models.PROTECT, related_name="reply_templates",
    )
    title = models.CharField(max_length=120)
    text = models.TextField()
    category = models.ForeignKey(
        ReplyTemplateCategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="templates",
    )
    tags = models.ManyToManyField(ReplyTemplateTag, through="ReplyTemplateTagLink")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]
        constraints = scoped_name_constraints("title", "reply_template")

    def clean(self):
        super().clean()
        if self.category_id and self.category.owner_id != self.owner_id:
            raise ValidationError({"category": "Template category must share its owner"})

    def __str__(self):
        return f"template:{self.organization_id}/{self.title}"


class ReplyTemplateTagLink(TenantRelationModel):
    tenant_relation_fields = ("template", "tag")
    template = models.ForeignKey(ReplyTemplate, on_delete=models.CASCADE)
    tag = models.ForeignKey(ReplyTemplateTag, on_delete=models.CASCADE)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["template", "tag"], name="uniq_reply_template_tag",
        )]

    def clean(self):
        super().clean()
        if self.template_id and self.tag_id and self.template.owner_id != self.tag.owner_id:
            raise ValidationError({"tag": "Template tag must share its owner"})

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"template-tag:{self.template_id}/{self.tag_id}"


class ReplyTemplateManagementGrant(TenantRelationModel):
    tenant_relation_fields = ("membership",)
    membership = models.OneToOneField(
        "identity.OrganizationMembership", on_delete=models.CASCADE,
        related_name="reply_template_management_grant",
    )

    def __str__(self):
        return f"template-management:{self.organization_id}/{self.membership_id}"
