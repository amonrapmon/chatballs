from chatballs.conversations.assignment_policy import AssignmentPolicy as AssignmentPolicy
from chatballs.conversations.comment_models import (
    ConversationComment as ConversationComment,
)
from chatballs.conversations.contact_models import (  # noqa: F401
    ConnectionIdentity,
    Contact,
    ContactFieldValue,
    ContactMerge,
)
from chatballs.conversations.conversation_models import (  # noqa: F401
    ControlMode,
    Conversation,
    ConversationLabel,
    ConversationPriority,
    ConversationRead,
    ExpectedResponder,
    LifecycleState,
)
from chatballs.conversations.domain_event_models import (  # noqa: F401
    ConversationEvent,
    ConversationEventHistoryStart,
)
from chatballs.conversations.email_attempt_models import (  # noqa: F401
    EmailSendAttempt,
    EmailSendOperation,
)
from chatballs.conversations.email_thread_models import (  # noqa: F401
    EmailThread,
    EmailThreadMessage,
)
from chatballs.conversations.message_models import (  # noqa: F401
    AiTurnState,
    DeliveryStatus,
    Message,
    MessageAuthor,
    MessageKind,
    TranscriptStatus,
)
from chatballs.conversations.participant_models import (
    ConversationParticipant as ConversationParticipant,
)

# Минимальный домен диалогов (ADR-CHATBALLS-0002/0003/0006). Состояние диалога
# разделено на независимые оси; перехват оператором — атомарный.
# Django импортирует только models.py: пороги очереди лежат рядом, чтобы не
# растить этот файл, и переэкспортируются здесь ради регистрации модели.
from chatballs.conversations.queue_models import (  # noqa: E402, F401
    QueueEscalationPolicy,
    policy_for,
)
from chatballs.conversations.rules.models import (  # noqa: F401
    HandlingRule,
    RuleExecution,
)
from chatballs.conversations.system_events import SystemEvent as SystemEvent
from chatballs.conversations.template_models import (  # noqa: E402, F401
    ReplyTemplate,
    ReplyTemplateCategory,
    ReplyTemplateManagementGrant,
    ReplyTemplateTag,
    ReplyTemplateTagLink,
)
from chatballs.conversations.transfer_models import (  # noqa: F401
    ConversationTransfer,
    TransferReason,
)
from chatballs.conversations.upload_paths import (  # noqa: F401
    contact_avatar_upload_path,
    message_attachment_upload_path,
    message_audio_upload_path,
)
