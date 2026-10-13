from django.urls import path

from . import views

urlpatterns = [
    path("settings/", views.QualitySettingsView.as_view()),
    path("report/", views.QualityReportView.as_view()),
    path("jobs/<int:job_id>/", views.QualityJobView.as_view()),
    path("jobs/<int:job_id>/corrections/", views.QualityCorrectionView.as_view()),
    path("jobs/<int:job_id>/messages/<int:message_id>/", views.QualityEvidenceView.as_view()),
]
