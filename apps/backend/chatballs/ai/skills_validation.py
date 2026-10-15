"""Whole-configuration validation before entering the save transaction."""

from rest_framework.exceptions import APIException

from chatballs.ai.skill_templates.engine import validate_templates
from chatballs.ai.skill_templates.limits import CONFIG_BYTES, bounded_json
from chatballs.i18n import t

INSTRUCTION_MAX = 32_768
REQUEST_MAX_BYTES = 160_000


class SkillError(APIException):
    def __init__(self, code, *, status=400, field=None):
        self.status_code = status
        detail = {"code": code, "detail": t(f"skills.{code}")}
        if field:
            detail["errors"] = [{"path": field, "code": code, "detail": t(f"skills.{code}")}]
        super().__init__(detail)


def configuration(raw):
    if not isinstance(raw, dict) or set(raw) != {"name", "description", "instruction", "templates"}:
        raise SkillError("invalid_configuration")
    result = {}
    for field, maximum in (("name", 60), ("description", 200), ("instruction", INSTRUCTION_MAX)):
        value = raw[field]
        if not isinstance(value, str) or not value.strip() or len(value) > maximum or "\0" in value:
            raise SkillError("invalid_field", field=field)
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise SkillError("invalid_field", field=field) from None
        result[field] = value.strip() if field != "instruction" else value
    bounded_json(raw, CONFIG_BYTES)
    result["templates"] = validate_templates(raw["templates"])
    return result


def expected_revision(raw):
    if type(raw) is not int or raw < 1 or raw > 2**63 - 1:
        raise SkillError("invalid_revision", field="expectedRevision")
    return raw
