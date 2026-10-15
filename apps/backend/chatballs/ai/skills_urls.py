from django.urls import path

from chatballs.ai.skills_preview import SkillBasisView, SkillPreviewView, SkillValidationView
from chatballs.ai.skills_views import (
    SkillAssignmentView,
    SkillDeletionView,
    SkillDetailView,
    SkillListView,
)

urlpatterns = [
    path("", SkillListView.as_view(), name="skill-list"),
    path("bases/orders/", SkillBasisView.as_view(), name="skill-order-basis"),
    path("validate/", SkillValidationView.as_view(), name="skill-validate"),
    path("preview/", SkillPreviewView.as_view(), name="skill-preview"),
    path("<uuid:skill_id>/", SkillDetailView.as_view(), name="skill-detail"),
    path("<uuid:skill_id>/validate/", SkillValidationView.as_view(), name="skill-validate-existing"),
    path("<uuid:skill_id>/preview/", SkillPreviewView.as_view(), name="skill-preview-existing"),
    path("<uuid:skill_id>/deletion/", SkillDeletionView.as_view(), name="skill-deletion"),
    path("<uuid:skill_id>/agents/<int:agent_id>/", SkillAssignmentView.as_view(), name="skill-assignment"),
]
