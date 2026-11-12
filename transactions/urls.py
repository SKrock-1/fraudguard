from django.urls import path
from transactions.views import TransactionIngestionView

urlpatterns = [
    path("", TransactionIngestionView.as_view(), name="transaction_ingest"),
]
