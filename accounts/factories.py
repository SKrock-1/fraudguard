from decimal import Decimal
import factory
from accounts.models import User, Account


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User
        django_get_or_create = ("username",)

    username = factory.Sequence(lambda n: f"user_{n}")
    email = factory.LazyAttribute(lambda o: f"{o.username}@example.com")
    first_name = "Test"
    last_name = "User"
    role = User.Role.INGESTION_CLIENT
    is_active = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        password = kwargs.pop("password", "defaultpassword123")
        user = super()._create(model_class, *args, **kwargs)
        user.set_password(password)
        user.save()
        return user


class AccountFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Account

    user = factory.SubFactory(UserFactory)
    account_number = factory.Sequence(lambda n: f"ACC_{n:06d}")
    avg_spend = Decimal("150.00")
    spend_stddev = Decimal("45.00")
    last_known_lat = Decimal("40.712776")
    last_known_lng = Decimal("-74.005974")
