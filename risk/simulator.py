"""
Synthetic transaction generator for demos and dashboard development.

Accounts get a home city and a spend profile; most traffic is ordinary spend
near home, with a small share of injected fraud patterns that the rule engine
is designed to catch:

- account_takeover: a large purchase from a distant city shortly after a
  home transaction (impossible travel + amount anomaly)
- card_testing: a rapid burst of small charges ending in a large one
  (velocity + amount anomaly)
- big_spend: a single purchase far above the account's normal range
"""
import logging
import random
import threading
import time
import uuid
from datetime import timedelta
from decimal import Decimal

from django.db import close_old_connections
from django.utils import timezone

logger = logging.getLogger(__name__)

CITIES = [
    ("New York", 40.7128, -74.0060),
    ("San Francisco", 37.7749, -122.4194),
    ("Chicago", 41.8781, -87.6298),
    ("London", 51.5074, -0.1278),
    ("Berlin", 52.5200, 13.4050),
    ("Mumbai", 19.0760, 72.8777),
    ("Singapore", 1.3521, 103.8198),
    ("Tokyo", 35.6762, 139.6503),
    ("Sydney", -33.8688, 151.2093),
    ("São Paulo", -23.5505, -46.6333),
    ("Toronto", 43.6532, -79.3832),
    ("Dubai", 25.2048, 55.2708),
]

EVERYDAY_MERCHANTS = [
    "Whole Foods Market", "Blue Bottle Coffee", "Uber", "Shell", "Target",
    "Amazon.com", "Spotify", "Netflix", "Walgreens", "Trader Joe's",
    "Chipotle", "Apple Store", "Lyft", "Costco", "Starbucks", "IKEA",
]
RISKY_MERCHANTS = [
    "CryptoXchange Ltd", "Luxe Watches Intl", "GiftCardHub", "Electro Wholesale",
    "WireNow Transfers", "Prestige Jewelers", "QuickGames Credits",
]

FRAUD_PATTERNS = ("account_takeover", "card_testing", "big_spend")


def _jitter(value: float, km: float = 15.0) -> Decimal:
    # ~0.009 degrees per km; keeps everyday spend inside the home metro
    return Decimal(str(round(value + random.uniform(-km, km) * 0.009, 6)))


def _money(value: float) -> Decimal:
    return Decimal(str(round(max(value, 1.0), 2)))


def _home_city(account):
    return CITIES[account.id % len(CITIES)]


def _make_txn(account, amount, merchant, lat, lng, ts):
    from transactions.models import Transaction
    return Transaction.objects.create(
        account=account,
        amount=_money(amount),
        currency="USD",
        merchant=merchant,
        lat=lat,
        lng=lng,
        timestamp=ts,
        idempotency_key=f"sim_{uuid.uuid4().hex}",
        status=Transaction.Status.PENDING,
    )


def generate_events(account, ts, pattern=None):
    """
    Build the (amount, merchant, lat, lng, ts) tuples for one event on an account.
    Normal events are a single transaction; fraud patterns may be several.
    """
    _, home_lat, home_lng = _home_city(account)
    avg = float(account.avg_spend) or 60.0
    std = float(account.spend_stddev) or avg * 0.35

    if pattern is None:
        amount = abs(random.gauss(avg, std * 0.8))
        return [(amount, random.choice(EVERYDAY_MERCHANTS), _jitter(home_lat), _jitter(home_lng), ts)]

    if pattern == "account_takeover":
        far = random.choice([c for c in CITIES if abs(c[1] - home_lat) + abs(c[2] - home_lng) > 40])
        return [
            (abs(random.gauss(avg, std * 0.5)), random.choice(EVERYDAY_MERCHANTS),
             _jitter(home_lat), _jitter(home_lng), ts),
            (avg * random.uniform(6, 14), random.choice(RISKY_MERCHANTS),
             _jitter(far[1], 3), _jitter(far[2], 3), ts + timedelta(minutes=random.randint(8, 40))),
        ]

    if pattern == "card_testing":
        merchant = random.choice(RISKY_MERCHANTS)
        lat, lng = _jitter(home_lat), _jitter(home_lng)
        burst = [
            (random.uniform(1, 9), merchant, lat, lng, ts + timedelta(seconds=20 * i))
            for i in range(6)
        ]
        burst.append((avg * random.uniform(5, 9), merchant, lat, lng, ts + timedelta(seconds=140)))
        return burst

    # big_spend
    return [(avg * random.uniform(7, 15), random.choice(RISKY_MERCHANTS),
             _jitter(home_lat), _jitter(home_lng), ts)]


def pick_pattern(fraud_rate: float):
    return random.choice(FRAUD_PATTERNS) if random.random() < fraud_rate else None


def run_live_stream(count: int, fraud_rate: float, duration_seconds: float) -> None:
    """
    Drip `count` events onto random accounts over `duration_seconds`, through the
    same create -> score_transaction.delay path the ingestion API uses, so the
    dashboard's WebSocket feed fills in real time.
    """
    from accounts.models import Account
    from risk.tasks import score_transaction

    close_old_connections()
    try:
        accounts = list(Account.objects.all())
        if not accounts:
            logger.warning("simulator: no accounts; run `manage.py seed_demo` first")
            return
        delay = duration_seconds / max(count, 1)
        for _ in range(count):
            account = random.choice(accounts)
            account.refresh_from_db()
            for amount, merchant, lat, lng, _ts in generate_events(account, timezone.now(), pick_pattern(fraud_rate)):
                # Live events use wall-clock time; the pattern's internal spacing
                # is compressed so bursts still look like bursts to the rules.
                txn = _make_txn(account, amount, merchant, lat, lng, timezone.now())
                score_transaction.delay(txn.id)
            time.sleep(delay * random.uniform(0.4, 1.6))
    except Exception:
        logger.exception("simulator: live stream failed")
    finally:
        close_old_connections()


_stream_lock = threading.Lock()
_active_stream = None


def start_live_stream(count: int = 30, fraud_rate: float = 0.25, duration_seconds: float = 30.0) -> bool:
    """Start a background stream; returns False if one is already running."""
    global _active_stream
    with _stream_lock:
        if _active_stream is not None and _active_stream.is_alive():
            return False
        _active_stream = threading.Thread(
            target=run_live_stream,
            args=(count, fraud_rate, duration_seconds),
            name="fraudguard-simulator",
            daemon=True,
        )
        _active_stream.start()
        return True


def stream_running() -> bool:
    return _active_stream is not None and _active_stream.is_alive()
