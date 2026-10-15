from django.urls import path

from chatballs.ai.skills_views import (
    SkillAssignmentView,
    SkillDeletionView,
    SkillDetailView,
    SkillListView,
)

urlpatterns = [
    path("", SkillListView.as_view(), name="skill-list"),
    path("<uuid:skill_id>/", SkillDetailView.as_view(), name="skill-detail"),
    path("<uuid:skill_id>/deletion/", SkillDeletionView.as_view(), name="skill-deletion"),
    path("<uuid:skill_id>/agents/<int:agent_id>/", SkillAssignmentView.as_view(), name="skill-assignment"),
]
