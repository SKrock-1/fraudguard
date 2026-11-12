from django.contrib import admin
from django.urls import path, include

from fraudguard.views import health
from risk.views import BacktestView, ModelVersionListView, RetrainView, SimulateTrafficView

urlpatterns = [
    path("api/health/", health, name="health"),
    path("api/demo/simulate/", SimulateTrafficView.as_view(), name="demo-simulate"),
    path("api/ml/models/", ModelVersionListView.as_view(), name="ml-models"),
    path("api/ml/backtest/", BacktestView.as_view(), name="ml-backtest"),
    path("api/ml/retrain/", RetrainView.as_view(), name="ml-retrain"),
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/transactions/", include("transactions.urls")),
    path("api/alerts/", include("alerts.urls")),
    path("api/audit/", include("audit.urls")),
]
