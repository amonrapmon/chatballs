"""Content-free diagnostics: never reflect source, data or parser exceptions."""

from rest_framework.exceptions import APIException

from chatballs.i18n import t


class TemplateError(APIException):
    status_code = 400

    def __init__(self, code, *, origin="configuration", tab="schema", path="", source=None, offset=0):
        error = {"code": code, "detail": t(f"skills.template_{code}"),
                 "origin": origin, "tab": tab, "path": path}
        if source is not None:
            error["line"] = source.count("\n", 0, offset) + 1
            error["column"] = offset - source.rfind("\n", 0, offset)
        super().__init__({"code": "invalid_template", "detail": error["detail"],
                          "origin": origin, "errors": [error]})

    @classmethod
    def combined(cls, errors):
        first = errors[0]
        result = cls(str(first["code"]), origin=str(first["origin"]), tab=str(first["tab"]))
        result.detail["errors"] = errors[:128]
        return result
