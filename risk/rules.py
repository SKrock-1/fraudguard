import math
import time
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple

from django.utils import timezone
from accounts.models import Account
from transactions.models import Transaction
from risk.redis_client import get_redis_client


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points
    on the Earth using the Haversine formula.
    """
    r_km = 6371.0  # Earth's mean radius in kilometers

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_km * c


def velocity_check(
    account: Account,
    window_minutes: int = 10,
    max_count: int = 5,
    redis_client: Optional[Any] = None,
    current_time: Optional[datetime] = None,
    txn_identifier: Optional[str] = None,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Evaluate transaction velocity using a sliding window stored in a Redis Sorted Set.

    Key: `velocity:{account_id}`
    Score: timestamp (epoch seconds)
    Member: unique transaction identifier

    Returns:
        (triggered: bool, detail: dict)
    """
    client = redis_client or get_redis_client()
    key = f"velocity:{account.id}"

    if current_time:
        if timezone.is_aware(current_time):
            now_ts = current_time.timestamp()
        else:
            now_ts = current_time.replace(tzinfo=timezone.utc).timestamp()
    else:
        now_ts = time.time()

    window_seconds = window_minutes * 60
    window_start = now_ts - window_seconds
    member_id = txn_identifier or str(uuid.uuid4())

    try:
        pipeline = client.pipeline()
        # 1. Prune timestamps older than the sliding window
        pipeline.zremrangebyscore(key, "-inf", window_start)
        # 2. Count active transactions in the current window before this one
        pipeline.zcard(key)
        # 3. Add this transaction to the sorted set
        pipeline.zadd(key, {member_id: now_ts})
        # 4. Set key expiration to 2x window duration for auto-cleanup
        pipeline.expire(key, window_seconds * 2)

        results = pipeline.execute()
        active_count = results[1]  # count before inserting current txn
        new_count = active_count + 1

        triggered = new_count > max_count

        detail = {
            "rule": "velocity",
            "count": new_count,
            "max_count": max_count,
            "window_minutes": window_minutes,
            "key": key,
        }
        return triggered, detail

    except Exception as exc:
        # Fallback if Redis is temporarily unreachable
        return False, {
            "rule": "velocity",
            "error": f"Redis velocity check failed: {str(exc)}",
            "count": 0,
            "max_count": max_count,
        }


def impossible_travel_check(
    account: Account,
    transaction: Transaction,
    max_speed_kmh: float = 800.0,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Flag if the implied travel speed between the account's last known location
    and the current transaction's location exceeds realistic commercial transit speeds.

    Returns:
        (triggered: bool, detail: dict)
    """
    # Check if both account and transaction have geo and timestamps
    if (
        account.last_known_lat is None
        or account.last_known_lng is None
        or account.last_transaction_at is None
    ):
        return False, {
            "rule": "impossible_travel",
            "reason": "missing_account_baseline_location_or_timestamp",
        }

    if transaction.lat is None or transaction.lng is None or transaction.timestamp is None:
        return False, {
            "rule": "impossible_travel",
            "reason": "missing_transaction_location_or_timestamp",
        }

    lat1 = float(account.last_known_lat)
    lon1 = float(account.last_known_lng)
    lat2 = float(transaction.lat)
    lon2 = float(transaction.lng)

    distance_km = haversine_distance(lat1, lon1, lat2, lon2)
    elapsed_seconds = (transaction.timestamp - account.last_transaction_at).total_seconds()

    # Same location requires negligible transit
    if distance_km < 1.0:
        return False, {
            "rule": "impossible_travel",
            "distance_km": round(distance_km, 2),
            "elapsed_seconds": round(elapsed_seconds, 2),
            "speed_kmh": 0.0,
            "max_speed_kmh": max_speed_kmh,
        }

    # If elapsed time is zero or negative with significant distance
    if elapsed_seconds <= 0:
        return True, {
            "rule": "impossible_travel",
            "distance_km": round(distance_km, 2),
            "elapsed_seconds": round(elapsed_seconds, 2),
            # None, not float("inf"): factors is a JSONField and Infinity isn't valid JSON
            "speed_kmh": None,
            "max_speed_kmh": max_speed_kmh,
            "reason": "instantaneous_displacement",
        }

    elapsed_hours = elapsed_seconds / 3600.0
    speed_kmh = distance_km / elapsed_hours
    triggered = speed_kmh > max_speed_kmh

    detail = {
        "rule": "impossible_travel",
        "distance_km": round(distance_km, 2),
        "elapsed_seconds": round(elapsed_seconds, 2),
        "speed_kmh": round(speed_kmh, 2),
        "max_speed_kmh": max_speed_kmh,
    }
    return triggered, detail


def amount_anomaly_check(
    account: Account,
    transaction: Transaction,
    threshold_z: float = 3.0,
) -> Tuple[bool, Dict[str, Any]]:
    """
    Calculate the z-score of this transaction's amount against the account's
    rolling average spend and standard deviation:
        z = (amount - avg_spend) / spend_stddev

    Returns:
        (triggered: bool, detail: dict)
    """
    amount = float(transaction.amount)
    avg_spend = float(account.avg_spend)
    spend_stddev = float(account.spend_stddev)

    # Edge case: no stddev established yet
    if spend_stddev <= 0:
        # If stddev is 0, flag if amount is abnormally large (e.g. > 5x avg_spend)
        if avg_spend > 0 and amount >= avg_spend * 5:
            return True, {
                "rule": "amount_anomaly",
                "z_score": None,
                "amount": amount,
                "avg_spend": avg_spend,
                "spend_stddev": spend_stddev,
                "reason": "zero_stddev_extreme_multiple",
            }
        return False, {
            "rule": "amount_anomaly",
            "z_score": 0.0,
            "amount": amount,
            "avg_spend": avg_spend,
            "spend_stddev": spend_stddev,
            "threshold_z": threshold_z,
        }

    z_score = (amount - avg_spend) / spend_stddev
    triggered = z_score >= threshold_z

    detail = {
        "rule": "amount_anomaly",
        "z_score": round(z_score, 2),
        "amount": amount,
        "avg_spend": avg_spend,
        "spend_stddev": spend_stddev,
        "threshold_z": threshold_z,
    }
    return triggered, detail


def evaluate_rules(
    account: Account,
    transaction: Transaction,
    redis_client: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Convenience function that evaluates all synchronous fraud rules on a transaction
    and returns an explainable breakdown of all triggered and non-triggered rules.
    """
    v_trig, v_det = velocity_check(
        account=account,
        redis_client=redis_client,
        current_time=transaction.timestamp,
        txn_identifier=transaction.idempotency_key,
    )
    t_trig, t_det = impossible_travel_check(account, transaction)
    a_trig, a_det = amount_anomaly_check(account, transaction)

    triggered_rules = []
    if v_trig:
        triggered_rules.append("velocity")
    if t_trig:
        triggered_rules.append("impossible_travel")
    if a_trig:
        triggered_rules.append("amount_anomaly")

    return {
        "any_triggered": bool(triggered_rules),
        "triggered_rules": triggered_rules,
        "factors": {
            "velocity": {"triggered": v_trig, "detail": v_det},
            "impossible_travel": {"triggered": t_trig, "detail": t_det},
            "amount_anomaly": {"triggered": a_trig, "detail": a_det},
        },
    }
