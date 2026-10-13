"""Accepted first-release scale and bounded customer/admin inputs."""

from rest_framework.exceptions import ValidationError

from chatballs.i18n import t

COMMENT_LIMIT = 2000


def validate_scale(scale):
    if not isinstance(scale, list) or len(scale) != 5:
        raise ValidationError(t("ratings.invalid_scale"))
    for number, choice in enumerate(scale, 1):
        if (not isinstance(choice, dict) or set(choice) != {"value", "label"}
                or type(choice["value"]) is not int or choice["value"] != number
                or not isinstance(choice["label"], str)
                or not 1 <= len(choice["label"].strip()) <= 120):
            raise ValidationError(t("ratings.invalid_scale"))
    return scale


def validate_settings(policy):
    if type(policy.enabled) is not bool:
        raise ValidationError(t("ratings.invalid_settings"))
    if type(policy.delay_seconds) is not int or not 0 <= policy.delay_seconds <= 604800:
        raise ValidationError(t("ratings.invalid_settings"))
    if not isinstance(policy.text, str) or len(policy.text) > 4000:
        raise ValidationError(t("ratings.invalid_settings"))
    if policy.scale or policy.enabled:
        validate_scale(policy.scale)
    if policy.enabled and not policy.text.strip():
        raise ValidationError(t("ratings.invalid_settings"))


def validate_response(data, scale):
    if not isinstance(data, dict) or set(data) - {"value", "comment"}:
        raise ValidationError(t("ratings.invalid_response"))
    value = data.get("value")
    comment = data.get("comment", "")
    if (type(value) is not int or value not in [choice["value"] for choice in scale]
            or not isinstance(comment, str) or len(comment) > COMMENT_LIMIT):
        raise ValidationError(t("ratings.invalid_response"))
    return str(value), comment
