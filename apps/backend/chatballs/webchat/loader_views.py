"""Раздача автономного лоадера с кэшем не дольше пяти минут."""

from django.http import HttpResponse
from django.views import View

from chatballs.webchat.loader import LOADER_JS

LOADER_MAX_AGE_SECONDS = 300


class WidgetLoaderView(View):
    def get(self, request) -> HttpResponse:
        response = HttpResponse(LOADER_JS, content_type="application/javascript; charset=utf-8")
        # Не дольше 5 минут: лоадер применяет оформление кнопки (SPEC-0021 R-11).
        response["Cache-Control"] = f"public, max-age={LOADER_MAX_AGE_SECONDS}"
        return response
