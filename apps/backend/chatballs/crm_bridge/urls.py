from django.urls import path

from chatballs.crm_bridge.api_views import (
    CRMConfigurationView,
    CRMContactLinksView,
    CRMConversationLinkView,
)
from chatballs.crm_bridge.write_views import (
    CRMBindingWriteView,
    CRMCompanyListWriteView,
    CRMCompanyWriteView,
    CRMProviderUpdateView,
)

urlpatterns = [
    path("provider/", CRMProviderUpdateView.as_view(), name="crm-bridge-provider-update"),
    path("companies/", CRMCompanyListWriteView.as_view(), name="crm-bridge-companies-write"),
    path("companies/<int:company_id>/", CRMCompanyWriteView.as_view(),
         name="crm-bridge-company-write"),
    path("bindings/<int:integration_id>/", CRMBindingWriteView.as_view(),
         name="crm-bridge-binding-write"),
    path("", CRMConfigurationView.as_view(), name="crm-bridge-config"),
    path("links/conversations/<int:conversation_id>/", CRMConversationLinkView.as_view(),
         name="crm-bridge-conversation-link"),
    path("links/contacts/<int:contact_id>/", CRMContactLinksView.as_view(),
         name="crm-bridge-contact-links"),
]
