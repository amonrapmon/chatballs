from django.urls import path

from chatballs.ratings.public_views import PublicRatingView

urlpatterns = [path("", PublicRatingView.as_view(), name="customer-rating")]
