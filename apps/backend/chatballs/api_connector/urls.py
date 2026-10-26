from django.urls import path

from chatballs.api_connector.views import ConnectorEventView
from chatballs.api_connector.file_download import ConnectorCommandAttachmentView

urlpatterns = [
    path(
        "organizations/<uuid:connector_organization_public_id>/integrations/<int:integration_id>/commands/<uuid:command_id>/attachment/",
        ConnectorCommandAttachmentView.as_view(),
        name="api-connector-command-attachment",
    ),
    path(
        "organizations/<uuid:connector_organization_public_id>/integrations/<int:integration_id>/events/",
        ConnectorEventView.as_view(),
        name="api-connector-events",
    ),
]
