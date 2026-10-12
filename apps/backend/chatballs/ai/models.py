import uuid

from django.core.exceptions import ValidationError
from django.db import models
from pgvector.django import VectorField

from chatballs.tenancy.models import TenantRelationModel

# Один основной агент на канал обработки (ADR-CHATBALLS-0023).

DEFAULT_AI_MODEL = "anthropic/claude-sonnet-4.6"

from chatballs.ai.agent_config import (  # noqa: E402, F401
    HISTORY_LIMIT_DEFAULT,
    HISTORY_LIMIT_MAX,
    AIAgentStatus,
    AnswerLanguage,
)

# AI работает только через провайдера организации (AIAgent.provider_integration).

# --- Знания: общая библиотека организации с иерархией категорий

# (ADR-CHATBALLS-0023, ADR-CHATBALLS-0041 §8: областей видимости по отделам нет) ---

class Knowledge(models.Model):

    organization = models.ForeignKey("identity.Organization", on_delete=models.PROTECT, related_name="knowledge_items")

    category = models.ForeignKey(

        "ai.KnowledgeCategory",

        on_delete=models.PROTECT,

        related_name="knowledge_items",

    )

    title = models.CharField(max_length=255)

    description = models.CharField(max_length=500, blank=True)

    content = models.TextField(blank=True)  # Markdown

    is_enabled = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:

        ordering = ["title"]

        verbose_name_plural = "knowledge"

    def __str__(self) -> str:

        return f"knowledge:{self.organization_id}/{self.title}"

    def save(self, *args: object, **kwargs: object) -> None:

        self.clean()

        super().save(*args, **kwargs)

    def clean(self) -> None:

        super().clean()

        if self.category_id is not None and self.category.organization_id != self.organization_id:

            raise ValidationError({"category": "Category belongs to another organization"})

# Django imports only models.py by convention. Re-export the related knowledge

# models after Knowledge exists so they are registered without growing this file.

from chatballs.ai.knowledge_models import (  # noqa: E402, F401
    KnowledgeCategory,
)


def attachment_upload_path(instance: "KnowledgeAttachment", filename: str) -> str:

    organization = instance.knowledge.organization

    return (

        f"organizations/{organization.public_id}/knowledge/"

        f"{instance.knowledge_id}/{instance.public_id}/{filename}"

    )

class KnowledgeAttachment(TenantRelationModel):

    tenant_relation_fields = ("knowledge",)

    knowledge = models.ForeignKey(Knowledge, on_delete=models.CASCADE, related_name="attachments")

    # Непредсказуемый идентификатор публичной ссылки скачивания (ADR-CHATBALLS-0023):

    # агент может отдать ссылку клиенту в мессенджер, где нет аутентификации установки.

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    file = models.FileField(upload_to=attachment_upload_path, max_length=512)

    # Оригинальное имя сохраняется и уникально в рамках знания: текст знания

    # ссылается на вложение по имени.

    original_name = models.CharField(max_length=255)

    content_type = models.CharField(max_length=128, blank=True)

    size = models.PositiveBigIntegerField(default=0)

    # Текст, извлечённый из файла (md/txt/pdf/docx) для retrieval-индексации.

    extracted_text = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ["original_name"]

        constraints = [models.UniqueConstraint(fields=["knowledge", "original_name"], name="uniq_attachment_knowledge_name")]

    def __str__(self) -> str:

        return f"attachment:{self.knowledge_id}/{self.original_name}"

    def public_url(self) -> str:

        # Абсолютная ссылка скачивания: уходит клиентам в мессенджеры, поэтому

        # строится от публичного адреса установки, а не от request.

        from django.urls import reverse

        from chatballs.identity.instance_settings import public_base_url

        path = reverse("ai-attachment-download", kwargs={"public_id": self.public_id})

        return public_base_url() + path

class KnowledgeFragment(TenantRelationModel):

    tenant_relation_fields = ("knowledge", "portal_article")

    # Чанк источника + его эмбеддинг (pgvector). ADR-CHATBALLS-0016. Источник — либо

    # знание библиотеки, либо опубликованная статья портала поддержки: обе

    # ветки индексируются одинаково, чтобы retrieval оставался одним запросом.

    # Перестраивается при каждом изменении содержимого источника.

    knowledge = models.ForeignKey(

        Knowledge,

        on_delete=models.CASCADE,

        related_name="fragments",

        null=True,

        blank=True,

    )

    portal_article = models.ForeignKey(

        "support_portals.PortalArticle",

        on_delete=models.CASCADE,

        related_name="fragments",

        null=True,

        blank=True,

    )

    chunk_index = models.PositiveIntegerField()

    content = models.TextField()

    # Размерность не фиксируется: совместимость локального и production embedding-провайдера.

    embedding = VectorField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:

        ordering = ["knowledge_id", "portal_article_id", "chunk_index"]

        constraints = [

            models.UniqueConstraint(

                fields=["knowledge", "chunk_index"], name="uniq_fragment_knowledge_chunk"

            ),

            models.UniqueConstraint(

                fields=["portal_article", "chunk_index"], name="uniq_fragment_article_chunk"

            ),

            models.CheckConstraint(

                condition=(

                    models.Q(knowledge__isnull=False, portal_article__isnull=True)

                    | models.Q(knowledge__isnull=True, portal_article__isnull=False)

                ),

                name="fragment_single_source",

            ),

        ]

    def __str__(self) -> str:

        source = (

            f"knowledge:{self.knowledge_id}"

            if self.knowledge_id

            else f"article:{self.portal_article_id}"

        )

        return f"fragment:{source}/{self.chunk_index}"

    @property

    def source_title(self) -> str:

        """Заголовок источника для цитирования в системном промпте."""

        if self.knowledge_id is not None:

            return self.knowledge.title

        revision = self.portal_article.published_revision

        return revision.title if revision is not None else self.portal_article.slug

# --- Агент канала: одна сущность, без релизов (ADR-CHATBALLS-0023) ---

from chatballs.ai.agent_models import AIAgent  # noqa: E402, F401
from chatballs.ai.assistance_models import (  # noqa: E402, F401
    ReplyAssistanceAttempt,
    ReplyAssistanceStatus,
    ReplySuggestion,
)

# --- LLM usage accounting (tokens, cost) ---
from chatballs.ai.diagnostic_models import TurnDiagnostic  # noqa: E402, F401
from chatballs.ai.invocation_models import (  # noqa: E402, F401
    LlmInvocation,
    LlmInvocationStatus,
)
from chatballs.ai.tool_models import AgentTool  # noqa: E402, F401
