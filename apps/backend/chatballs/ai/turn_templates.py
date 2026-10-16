"""Internal preparation: loaded snapshot only, bounded restoration before rendering."""

import json
import re
import time
import uuid

from chatballs.ai.prepared_reply import PREPARED_PREFIX, PreparedReply, final_selection
from chatballs.ai.provider.base import ProviderError, ToolSpec
from chatballs.ai.skill_templates.engine import render_template
from chatballs.ai.skill_templates.errors import TemplateError
from chatballs.ai.skill_templates.limits import DATA_BYTES, bounded_json
from chatballs.ai.turn_skills import encoded

PREPARE_REPLY = "chatballs_prepare_reply"
WHOLE_TOKEN = re.compile(r"\[\[[^\[\]\n]{1,80}\]\]\Z")
TEMPLATE_RULES = (
    "Шаблоны загруженного навыка доступны через {operation}: передай skill_id, template_id и data по схеме. "
    "Не передавай HTML. Подготовка ничего не отправляет. Для выбора одного готового ответа верни "
    "ТОЛЬКО значение final_response из успешной подготовки, при передаче человеку добавь <<HANDOFF>>. "
    "Не переписывай разметку и не объединяй карточку с отдельным текстом. Для обычного ответа верни текст. "
    "При ошибке исправь данные в общем лимите либо уточни/передай человеку; не выдумывай факты."
)


def restore_data(schema, data, pseudonymizer):
    bounded_json(data, DATA_BYTES, origin="data")

    def restore(node, value):
        if isinstance(value, str):
            restored = pseudonymizer.restore(value)
            if restored.removed:
                raise TemplateError("invalid_value", origin="data")
            # A numeric tool result can have been masked as a whole JSON token.
            # Ordinary strings are never coerced to numbers or booleans.
            if node.get("type") == "number" and WHOLE_TOKEN.fullmatch(value) and restored.text != value:
                try:
                    number = json.loads(restored.text)
                except ValueError:
                    raise TemplateError("type", origin="data") from None
                if type(number) not in (int, float):
                    raise TemplateError("type", origin="data")
                return number
            return restored.text
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                if not isinstance(key, str):
                    raise TemplateError("type", origin="data")
                restored = pseudonymizer.restore(key)
                if restored.removed or restored.text in result:
                    raise TemplateError("invalid_value", origin="data")
                result[restored.text] = restore(node.get("properties", {}).get(restored.text, {}), child)
            return result
        if isinstance(value, list):
            return [restore(node.get("items", {}), child) for child in value]
        return value

    return restore(schema, data)


class TurnTemplates:
    """Mutable execution state is local to one run, never to the immutable plan."""

    def __init__(self, skills, tools, pseudonymizer, *, language):
        self.skills, self.pseudonymizer, self.language = skills, pseudonymizer, language
        self.loaded = set()
        self.prepared = {}
        self.enabled = skills.enabled and any(item.templates for item in skills.items)
        names = {tool.spec.name for tool in tools} | {skills.operation}
        self.operation = PREPARE_REPLY
        suffix = 1
        while self.operation in names:
            self.operation = f"{PREPARE_REPLY}_{suffix}"
            suffix += 1

    def spec(self):
        return ToolSpec(name=self.operation, description="Prepare one reply using a loaded skill template.", parameters={
            "type": "object", "properties": {
                "skill_id": {"type": "string"}, "template_id": {"type": "string"}, "data": {"type": "object"},
            }, "required": ["skill_id", "template_id", "data"], "additionalProperties": False,
        })

    def load(self, arguments, *, time_left):
        content = self.skills.load(arguments, self.pseudonymizer, time_left=time_left)
        if "error" not in json.loads(content):
            self.loaded.add(self.pseudonymizer.restore(arguments["skill_id"]).text)
        return content

    def prepare(self, arguments, *, time_left):
        started = time.monotonic()
        if time_left is not None and time_left <= 0:
            return encoded({"error": "timeout"})
        if (not isinstance(arguments, dict) or set(arguments) != {"skill_id", "template_id", "data"}
                or any(not isinstance(arguments[key], str) or len(arguments[key]) > 512
                       for key in ("skill_id", "template_id"))):
            return encoded({"error": "invalid_arguments"})
        skill_id = self.pseudonymizer.restore(arguments["skill_id"]).text
        template_id = self.pseudonymizer.restore(arguments["template_id"]).text
        skill = next((item for item in self.skills.items if item.id == skill_id), None)
        if not self.enabled or skill is None or skill_id not in self.loaded:
            return encoded({"error": "template_unavailable"})
        template = next((item for item in map(json.loads, skill.templates) if item["id"] == template_id), None)
        if template is None:
            return encoded({"error": "template_unavailable"})
        try:
            data = restore_data(template["schema"], arguments["data"], self.pseudonymizer)
            rendered = render_template(template, data, language=self.language)
            if not rendered["text"].strip():
                raise TemplateError("required", origin="data")
        except TemplateError as error:
            # No source, data, field names or exceptions are reflected to the model.
            return encoded({"error": "invalid_template_data", "code": str(error.detail["errors"][0]["code"])})
        if time_left is not None and time.monotonic() - started >= time_left:
            return encoded({"error": "timeout"})
        selector = PREPARED_PREFIX + uuid.uuid4().hex
        self.prepared[selector] = PreparedReply(
            rendered["text"], rendered["contentHtml"], encoded(rendered["presentation"]),
            encoded({"skillId": skill.id, "skillRevision": skill.revision,
                     "id": template["id"], "name": template["name"]}),
        )
        return encoded({"final_response": selector})

    def select(self, text):
        prepared = final_selection(text, self.prepared)
        if PREPARED_PREFIX in text and prepared is None:
            raise ProviderError("invalid prepared reply selection")
        return prepared
