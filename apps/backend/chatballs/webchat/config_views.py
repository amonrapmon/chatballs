"""Публичная конфигурация для iframe и лоадера на сайте организации."""

from django.utils.cache import patch_vary_headers
from rest_framework.request import Request
from rest_framework.response import Response

from chatballs.webchat import services
from chatballs.webchat.access import _Public, _resolved_web_widget
from chatballs.webchat.api_inputs import host_origin
from chatballs.webchat.throttling import WebchatConfigThrottle


class WebchatConfigView(_Public):
    throttle_classes = [WebchatConfigThrottle]

    def get(self, request: Request) -> Response:
        widget_key = request.GET.get("widgetKey", "")
        channel_code = request.GET.get("channel", "")
        with _resolved_web_widget(widget_key, channel_code) as (context, widget):
            if context is None or widget is None:
                response = Response({"available": False})
            else:
                response = Response(
                    services.public_config(
                        context=context, widget=widget, origin=host_origin(request),
                    )
                )
        # Лоадер работает на другом домене. CORS разрешается только для
        # конфигурации доступного этому сайту виджета, без cookies и сессии.
        origin = request.headers.get("Origin")
        if origin and response.data.get("available"):
            response["Access-Control-Allow-Origin"] = origin
        patch_vary_headers(response, ["Origin"])
        response["Cache-Control"] = "no-cache"
        return response
