"""Reject unresolved template markers before any outgoing-message side effects."""

from chatballs.conversations.template_variables import is_known_variable, variable_keys
from chatballs.i18n import t


class UnfilledTemplateVariables(ValueError):
    def __init__(self, keys):
        self.keys = keys
        super().__init__(t("conversations.template_unfilled_variables"))

    def payload(self):
        return {"detail": str(self), "unfilledKeys": self.keys}


def require_filled_text(text):
    keys = [key for key in variable_keys(text) if is_known_variable(key)]
    if keys:
        raise UnfilledTemplateVariables(keys)
