from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from accounts.permissions import IsIngestionClient
from accounts.throttles import PerClientIngestionThrottle
from transactions.models import Transaction
from transactions.serializers import (
    TransactionIngestionSerializer,
    TransactionResponseSerializer,
)


class TransactionIngestionView(APIView):
    """
    Ingest a financial transaction with strict idempotency guarantees.

    - If idempotency_key is already present in DB: returns existing record with HTTP 200 OK.
    - If idempotency_key is new: creates transaction with status 'pending', enqueues
      scoring via Celery, and returns HTTP 202 Accepted.
    - Protected by IsIngestionClient permission (role: ingestion_client or admin).
    - Rate-limited per API client via PerClientIngestionThrottle.
    """
    permission_classes = [IsIngestionClient]
    throttle_classes = [PerClientIngestionThrottle]

    def post(self, request, *args, **kwargs):
        serializer = TransactionIngestionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated_data = serializer.validated_data
        idempotency_key = validated_data["idempotency_key"]
        account = validated_data["account_number"]  # validated to Account instance

        # Fast path: Check if idempotency_key already exists
        existing_txn = Transaction.objects.filter(idempotency_key=idempotency_key).first()
        if existing_txn:
            return Response(
                TransactionResponseSerializer(existing_txn).data,
                status=status.HTTP_200_OK,
            )

        # Create new transaction handling concurrent collisions atomically
        try:
            with transaction.atomic():
                txn = Transaction.objects.create(
                    account=account,
                    amount=validated_data["amount"],
                    currency=validated_data.get("currency", "USD"),
                    merchant=validated_data["merchant"],
                    lat=validated_data.get("lat"),
                    lng=validated_data.get("lng"),
                    timestamp=validated_data.get("timestamp"),
                    idempotency_key=idempotency_key,
                    status=Transaction.Status.PENDING,
                )

            # Enqueue async scoring AFTER the transaction is committed
            from risk.tasks import score_transaction
            score_transaction.delay(txn.id)

            return Response(
                TransactionResponseSerializer(txn).data,
                status=status.HTTP_202_ACCEPTED,
            )
        except IntegrityError:
            # Another concurrent request with the same idempotency_key inserted first
            existing_txn = Transaction.objects.get(idempotency_key=idempotency_key)
            return Response(
                TransactionResponseSerializer(existing_txn).data,
                status=status.HTTP_200_OK,
            )
