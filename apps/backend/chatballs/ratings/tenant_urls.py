from django.urls import path

from chatballs.ratings.tenant_views import (
    ConversationRatingsView,
    RatingResultsView,
    RatingSettingsView,
)

urlpatterns = [
    path("settings/", RatingSettingsView.as_view()),
    path("results/", RatingResultsView.as_view()),
    path("conversations/<int:conversation_id>/", ConversationRatingsView.as_view()),
]
