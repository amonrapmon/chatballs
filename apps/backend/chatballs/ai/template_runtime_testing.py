"""Small template and provider helpers for the isolated behavior tests."""

import json

from chatballs.ai.tool_loop_testing import ScriptedProvider, says

TEMPLATE_ID = "e805a26b-b3d2-4149-b2ae-5d508153679e"


def reply_template():
    return {
        "id": TEMPLATE_ID, "name": "Status", "purpose": "Show trusted status",
        "schema": {"type": "object", "properties": {
            "title": {"type": "string", "required": True},
            "amount": {"type": "number", "required": True},
            "active": {"type": "boolean", "required": True},
            "url": {"type": "string"},
        }},
        "html": '<div class="card"><b>{{ title }}</b> {{ amount }} {{ active }}{{#if url}}<a href="{{ url }}">Link</a>{{/if}}</div>',
        "css": ".card{color:blue}", "text": "{{ title }} {{ amount }} {{ active }}", "examples": [],
    }


class SelectingProvider(ScriptedProvider):
    def chat(self, *, messages, model, params=None, tools=None):
        if messages[-1].role == "tool":
            result = json.loads(messages[-1].content)
            if "final_response" in result:
                self.steps = [says(result["final_response"])]
        return super().chat(messages=messages, model=model, params=params, tools=tools)
