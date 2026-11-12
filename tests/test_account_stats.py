"""Rolling spend statistics (Welford update) edge cases."""
import statistics
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.utils import timezone

from accounts.factories import AccountFactory


def _txn(amount):
    return SimpleNamespace(amount=Decimal(amount), timestamp=timezone.now(), lat=None, lng=None)


def test_first_transaction_with_float_residue_does_not_crash(db):
    """Regression: 260.00 baseline then 6.44 made m2 = -6.8e-13 and sqrt went complex."""
    acct = AccountFactory(avg_spend=Decimal("260.00"), spend_stddev=Decimal("85.31"))
    acct.record_transaction(_txn("6.44"), prior_count=0)
    assert acct.avg_spend == Decimal("6.44")
    assert acct.spend_stddev == Decimal("0.0")


@pytest.mark.parametrize("amounts", [["10.00", "20.00", "30.00"], ["6.44", "6.44", "6.45", "1999.99"]])
def test_matches_population_statistics(db, amounts):
    acct = AccountFactory(avg_spend=Decimal("0"), spend_stddev=Decimal("0"))
    for i, a in enumerate(amounts):
        acct.record_transaction(_txn(a), prior_count=i)
    values = [float(a) for a in amounts]
    assert float(acct.avg_spend) == pytest.approx(statistics.fmean(values), abs=0.01)
    assert float(acct.spend_stddev) == pytest.approx(statistics.pstdev(values), abs=0.02)
