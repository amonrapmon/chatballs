"""Remove render inputs and tool results before diagnostic redaction/storage."""

from copy import deepcopy


def without_operation_data(payload):
    payload = deepcopy(payload)
    for message in payload.get("messages", []):
        if message.get("role") == "tool":
            message["content"] = "[operation result omitted]"
        elif message.get("tool_calls"):
            message["content"] = ""
        for call in message.get("tool_calls") or []:
            call["arguments"] = {}
    if payload.get("tool_calls"):
        payload["text"] = ""
    for call in payload.get("tool_calls") or []:
        call["arguments"] = {}
    return payload
