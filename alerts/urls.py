from django.urls import path
from alerts.views import AlertListView, AlertDetailView, AlertReviewView, AlertStatsView

urlpatterns = [
    path("", AlertListView.as_view(), name="alert-list"),
    path("stats/", AlertStatsView.as_view(), name="alert-stats"),
    path("<int:alert_id>/", AlertDetailView.as_view(), name="alert-detail"),
    path("<int:alert_id>/review/", AlertReviewView.as_view(), name="alert-review"),
]
