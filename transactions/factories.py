from decimal import Decimal
import uuid
import factory
from django.utils import timezone
from accounts.factories import AccountFactory
from transactions.models import Transaction


class TransactionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Transaction

    account = factory.SubFactory(AccountFactory)
    amount = Decimal("99.99")
    currency = "USD"
    merchant = "Amazon.com"
    lat = Decimal("40.712776")
    lng = Decimal("-74.005974")
    timestamp = factory.LazyFunction(timezone.now)
    idempotency_key = factory.LazyFunction(lambda: str(uuid.uuid4()))
    status = Transaction.Status.PENDING
