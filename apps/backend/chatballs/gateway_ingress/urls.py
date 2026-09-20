from django.urls import path

from .views import GatewayDeliveryStatusView, GatewayInboundView

urlpatterns = [
    path(
        "integrations/<int:integration_id>/inbound/",
        GatewayInboundView.as_view(),
        name="gateway-inbound",
    ),
    path(
        "integrations/<int:integration_id>/delivery-status/",
        GatewayDeliveryStatusView.as_view(),
        name="gateway-delivery-status",
    ),
]
