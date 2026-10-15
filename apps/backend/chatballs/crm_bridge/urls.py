from django.urls import path

from chatballs.crm_bridge.api_views import (
    CRMConfigurationView,
    CRMContactLinksView,
    CRMConversationLinkView,
)

urlpatterns = [
    path("", CRMConfigurationView.as_view(), name="crm-bridge-config"),
    path("links/conversations/<int:conversation_id>/", CRMConversationLinkView.as_view(),
         name="crm-bridge-conversation-link"),
    path("links/contacts/<int:contact_id>/", CRMContactLinksView.as_view(),
         name="crm-bridge-contact-links"),
]
