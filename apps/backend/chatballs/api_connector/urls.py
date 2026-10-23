from django.urls import path

from chatballs.api_connector.views import ConnectorEventView

urlpatterns = [
    path(
        "organizations/<uuid:connector_organization_public_id>/integrations/<int:integration_id>/events/",
        ConnectorEventView.as_view(),
        name="api-connector-events",
    ),
]
