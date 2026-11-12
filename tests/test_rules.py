from datetime import timedelta
from decimal import Decimal
import pytest
from django.utils import timezone
from accounts.factories import AccountFactory
from transactions.factories import TransactionFactory
from risk.rules import (
    velocity_check,
    impossible_travel_check,
    amount_anomaly_check,
    evaluate_rules,
    haversine_distance,
)


# --- Haversine Distance Tests ---

def test_haversine_distance():
    # NYC to London is approximately 5,570 km
    nyc_lat, nyc_lng = 40.7128, -74.0060
    lon_lat, lon_lng = 51.5074, -0.1278
    dist = haversine_distance(nyc_lat, nyc_lng, lon_lat, lon_lng)
    assert 5500 < dist < 5650

    # Same location
    assert haversine_distance(nyc_lat, nyc_lng, nyc_lat, nyc_lng) == 0.0


# --- Velocity Check Tests ---

def test_velocity_check_benign(fake_redis):
    account = AccountFactory()
    base_time = timezone.now()

    # Submit 3 transactions within a 10 minute window (max_count=5)
    for i in range(3):
        triggered, detail = velocity_check(
            account=account,
            window_minutes=10,
            max_count=5,
            redis_client=fake_redis,
            current_time=base_time + timedelta(minutes=i),
            txn_identifier=f"txn_{i}",
        )

    assert triggered is False
    assert detail["count"] == 3
    assert detail["max_count"] == 5
    assert detail["rule"] == "velocity"


def test_velocity_check_fraudulent(fake_redis):
    account = AccountFactory()
    base_time = timezone.now()

    # Submit 6 transactions in rapid succession (max_count=5)
    results = []
    for i in range(6):
        triggered, detail = velocity_check(
            account=account,
            window_minutes=10,
            max_count=5,
            redis_client=fake_redis,
            current_time=base_time + timedelta(seconds=i * 10),
            txn_identifier=f"rapid_txn_{i}",
        )
        results.append(triggered)

    # First 5 should be False, 6th should be True
    assert results[:5] == [False, False, False, False, False]
    assert results[5] is True
    assert detail["count"] == 6
    assert detail["max_count"] == 5


def test_velocity_check_sliding_window_expiration(fake_redis):
    account = AccountFactory()
    base_time = timezone.now()

    # 4 transactions at t = 0
    for i in range(4):
        velocity_check(
            account=account,
            window_minutes=10,
            max_count=5,
            redis_client=fake_redis,
            current_time=base_time,
            txn_identifier=f"old_txn_{i}",
        )

    # 2 transactions 15 minutes later (older transactions have expired out of the 10-min window)
    later_time = base_time + timedelta(minutes=15)
    for i in range(2):
        triggered, detail = velocity_check(
            account=account,
            window_minutes=10,
            max_count=5,
            redis_client=fake_redis,
            current_time=later_time + timedelta(seconds=i),
            txn_identifier=f"new_txn_{i}",
        )

    assert triggered is False
    assert detail["count"] == 2  # Only the 2 recent transactions counted


# --- Impossible Travel Tests ---

def test_impossible_travel_benign():
    now = timezone.now()
    # NYC to Brooklyn: ~10 km apart, 45 minutes elapsed -> speed ~13.3 km/h
    account = AccountFactory(
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now - timedelta(minutes=45),
    )
    transaction = TransactionFactory(
        account=account,
        lat=Decimal("40.6782"),
        lng=Decimal("-73.9442"),
        timestamp=now,
    )

    triggered, detail = impossible_travel_check(account, transaction, max_speed_kmh=800.0)
    assert triggered is False
    assert detail["speed_kmh"] < 100.0
    assert detail["distance_km"] > 0


def test_impossible_travel_fraudulent():
    now = timezone.now()
    # NYC to London (~5,570 km) in 30 minutes -> speed > 11,000 km/h
    account = AccountFactory(
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now - timedelta(minutes=30),
    )
    transaction = TransactionFactory(
        account=account,
        lat=Decimal("51.5074"),
        lng=Decimal("-0.1278"),
        timestamp=now,
    )

    triggered, detail = impossible_travel_check(account, transaction, max_speed_kmh=800.0)
    assert triggered is True
    assert detail["speed_kmh"] > 10000.0
    assert detail["max_speed_kmh"] == 800.0


def test_impossible_travel_instantaneous_displacement():
    now = timezone.now()
    # 0 seconds elapsed between NYC and London -> infinite speed
    account = AccountFactory(
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now,
    )
    transaction = TransactionFactory(
        account=account,
        lat=Decimal("51.5074"),
        lng=Decimal("-0.1278"),
        timestamp=now,
    )

    triggered, detail = impossible_travel_check(account, transaction)
    assert triggered is True
    assert detail["reason"] == "instantaneous_displacement"


def test_impossible_travel_missing_coords():
    now = timezone.now()
    account = AccountFactory(
        last_known_lat=None,
        last_known_lng=None,
        last_transaction_at=now,
    )
    transaction = TransactionFactory(
        account=account,
        lat=Decimal("40.7128"),
        lng=Decimal("-74.0060"),
    )

    triggered, detail = impossible_travel_check(account, transaction)
    assert triggered is False
    assert "missing" in detail["reason"]


# --- Amount Anomaly Tests ---

def test_amount_anomaly_benign():
    # Mean: $100, Stddev: $30. Amount: $130 -> z-score = 1.0 (threshold = 3.0)
    account = AccountFactory(
        avg_spend=Decimal("100.00"),
        spend_stddev=Decimal("30.00"),
    )
    transaction = TransactionFactory(account=account, amount=Decimal("130.00"))

    triggered, detail = amount_anomaly_check(account, transaction, threshold_z=3.0)
    assert triggered is False
    assert detail["z_score"] == 1.0
    assert detail["threshold_z"] == 3.0


def test_amount_anomaly_fraudulent():
    # Mean: $100, Stddev: $30. Amount: $2,500 -> z-score = 80.0 (threshold = 3.0)
    account = AccountFactory(
        avg_spend=Decimal("100.00"),
        spend_stddev=Decimal("30.00"),
    )
    transaction = TransactionFactory(account=account, amount=Decimal("2500.00"))

    triggered, detail = amount_anomaly_check(account, transaction, threshold_z=3.0)
    assert triggered is True
    assert detail["z_score"] == 80.0
    assert detail["threshold_z"] == 3.0


def test_amount_anomaly_zero_stddev():
    # Mean: $50, Stddev: $0. Amount: $1000 (20x average) -> triggers extreme multiple
    account = AccountFactory(
        avg_spend=Decimal("50.00"),
        spend_stddev=Decimal("0.00"),
    )
    transaction = TransactionFactory(account=account, amount=Decimal("1000.00"))

    triggered, detail = amount_anomaly_check(account, transaction)
    assert triggered is True
    assert detail["reason"] == "zero_stddev_extreme_multiple"


# --- Evaluate Rules (Combined) Test ---

def test_evaluate_rules_combined(fake_redis):
    now = timezone.now()
    account = AccountFactory(
        avg_spend=Decimal("100.00"),
        spend_stddev=Decimal("20.00"),
        last_known_lat=Decimal("40.7128"),
        last_known_lng=Decimal("-74.0060"),
        last_transaction_at=now - timedelta(minutes=10),
    )
    # Fraudulent on both amount ($1000, z=45) and impossible travel (London in 10 mins)
    transaction = TransactionFactory(
        account=account,
        amount=Decimal("1000.00"),
        lat=Decimal("51.5074"),
        lng=Decimal("-0.1278"),
        timestamp=now,
    )

    result = evaluate_rules(account, transaction, redis_client=fake_redis)
    assert result["any_triggered"] is True
    assert "impossible_travel" in result["triggered_rules"]
    assert "amount_anomaly" in result["triggered_rules"]
    assert "velocity" in result["factors"]
    assert "impossible_travel" in result["factors"]
    assert "amount_anomaly" in result["factors"]
    assert result["factors"]["amount_anomaly"]["triggered"] is True
    assert result["factors"]["impossible_travel"]["triggered"] is True
