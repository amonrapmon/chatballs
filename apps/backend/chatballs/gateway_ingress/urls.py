from django.urls import path

from .views import GatewayInboundView

urlpatterns = [
    path(
        "integrations/<int:integration_id>/inbound/",
        GatewayInboundView.as_view(),
        name="gateway-inbound",
    ),
]
