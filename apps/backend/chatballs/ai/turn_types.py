"""In-memory plans and results shared by live and verification turns."""

from dataclasses import dataclass, field

from chatballs.ai.diagnostic_redaction import DiagnosticRedactor
from chatballs.ai.invocation_jobs import ChatJob
from chatballs.ai.prepared_reply import PreparedReply
from chatballs.ai.provider.base import ChatResult, EmbeddingResult, ProviderError
from chatballs.ai.pseudonymization import Pseudonymizer
from chatballs.ai.tool_calls import ToolCallRecord
from chatballs.ai.tool_loop import ChatRound
from chatballs.ai.turn_skills import TurnSkills
from chatballs.ai.turn_tools import TurnTool


@dataclass(frozen=True, slots=True)
class QueryEmbedding:
    """Вектор вопроса. Пустой вектор — обычное дело: остаётся лексический поиск."""

    vector: list[float] | None = None
    model: str = ""
    latency_ms: int = 0
    results: list[EmbeddingResult] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TurnPlan:
    """Готовый запрос к модели и то, на чём он основан."""

    job: ChatJob
    fragment_ids: list[int]
    # Карта токенов хода: только в памяти, для обратной подстановки в ответ.
    pseudonymizer: Pseudonymizer
    # Инструменты, которые модель может вызвать в этом ходе (SPEC-0023 R-11).
    tools: list[TurnTool] = field(default_factory=list)
    skills: TurnSkills = field(default_factory=TurnSkills, repr=False)
    diagnostic_snapshot: dict = field(default_factory=dict)
    diagnostic_redactor: DiagnosticRedactor | None = field(default=None, repr=False)
    language: str = "en"


@dataclass(frozen=True, slots=True)
class TurnAnswer:
    """Итог похода к модели: либо ответ, либо отказ, и сколько это заняло."""

    result: ChatResult | None = None
    error: ProviderError | None = None
    latency_ms: int = 0
    # Ход с инструментами — несколько обращений к модели; без них — одно.
    rounds: tuple[ChatRound, ...] = ()
    # Вызовы инструментов хода, по порядку: для ленты оператора.
    tool_calls: tuple[ToolCallRecord, ...] = ()
    requests: tuple[ChatJob, ...] = field(default=(), repr=False)
    prepared_reply: PreparedReply | None = field(default=None, repr=False)
