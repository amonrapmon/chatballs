"""Bounded HTTP bodies use strict JSON without silently overwritten fields."""

import json

from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError


class SkillJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        try:
            return json.load(stream, object_pairs_hook=unique_object, parse_constant=reject_constant)
        except (ValueError, UnicodeError, RecursionError):
            raise ParseError("invalid_request") from None
