"""
Seed demo users, accounts and ~24h of scored transaction history so the
analyst dashboard has something to show.

    python manage.py seed_demo            # first run
    python manage.py seed_demo --reset    # wipe transactions/accounts and reseed

Demo logins use the password from the DEMO_PASSWORD environment variable.
"""
import os
import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction as db_transaction
from django.utils import timezone

from accounts.models import Account, User
from alerts.models import Alert
from audit.models import AuditLog
from risk import simulator
from risk.tasks import score_transaction
from transactions.models import Transaction

DEMO_USERS = [
    ("maya.chen", User.Role.ANALYST, "Maya", "Chen"),
    ("dev.patel", User.Role.ANALYST, "Dev", "Patel"),
    ("ops.admin", User.Role.ADMIN, "Ops", "Admin"),
    ("ingest-gateway", User.Role.INGESTION_CLIENT, "Ingest", "Gateway"),
]
HOLDER_USERNAME = "demo-cardholders"


class Command(BaseCommand):
    help = "Seed demo users, accounts and 24h of scored transactions for the dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--accounts", type=int, default=36)
        parser.add_argument("--events", type=int, default=520, help="Events across the last 24h")
        parser.add_argument("--fraud-rate", type=float, default=0.12)
        parser.add_argument("--reset", action="store_true", help="Delete existing transactions and accounts first")
        parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducible data")
        parser.add_argument("--if-empty", action="store_true", help="Do nothing (exit 0) if transactions already exist")

    def handle(self, *args, **opts):
        password = os.getenv("DEMO_PASSWORD", "").strip()
        if not password:
            raise CommandError("Set DEMO_PASSWORD (see .env.example) before seeding demo users.")
        if opts["seed"] is not None:
            random.seed(opts["seed"])

        if opts["reset"]:
            # AuditLog rows are insert-only and survive a reset by design.
            Transaction.objects.all().delete()
            Account.objects.all().delete()
            self.stdout.write("Cleared transactions and accounts.")
        elif Transaction.objects.exists():
            if opts["if_empty"]:
                self.stdout.write("Transactions already exist; skipping demo seed.")
                return
            raise CommandError("Transactions already exist; pass --reset to reseed.")

        users = self._ensure_users(password)
        accounts = self._create_accounts(opts["accounts"])
        fraud_txn_ids = self._backfill(accounts, opts["events"], opts["fraud_rate"])
        self._resolve_history(fraud_txn_ids, [u for u in users if u.role == User.Role.ANALYST])

        alerts = Alert.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f"Seeded {len(accounts)} accounts, {Transaction.objects.count()} transactions, {alerts} alerts. "
            f"Demo logins: {', '.join(u.username for u in users)}"
        ))

    def _ensure_users(self, password):
        users = []
        for username, role, first, last in DEMO_USERS:
            user, _ = User.objects.get_or_create(username=username)
            user.role, user.first_name, user.last_name = role, first, last
            user.email = f"{username.replace('-', '.')}@fraudguard.test"
            user.is_staff = role == User.Role.ADMIN
            user.set_password(password)
            user.save()
            users.append(user)
        return users

    def _create_accounts(self, count):
        holder, _ = User.objects.get_or_create(
            username=HOLDER_USERNAME, defaults={"role": User.Role.INGESTION_CLIENT}
        )
        holder.set_unusable_password()
        holder.save()

        start = timezone.now() - timedelta(hours=26)
        accounts = []
        for i in range(count):
            avg = random.choice([28, 45, 60, 85, 120, 180, 260])
            account = Account.objects.create(
                user=holder,
                account_number=f"FG-{random.randint(1000, 9999)}-{i:04d}",
                avg_spend=Decimal(str(avg)),
                spend_stddev=Decimal(str(round(avg * random.uniform(0.25, 0.45), 2))),
                last_transaction_at=start,
            )
            _, lat, lng = simulator._home_city(account)
            account.last_known_lat = Decimal(str(lat))
            account.last_known_lng = Decimal(str(lng))
            account.save(update_fields=["last_known_lat", "last_known_lng"])
            accounts.append(account)
        return accounts

    def _backfill(self, accounts, events, fraud_rate):
        now = timezone.now()
        planned = []
        for _ in range(events):
            account = random.choice(accounts)
            # Busier during the day (UTC), quieter overnight
            minutes_ago = random.triangular(0, 24 * 60, 9 * 60)
            ts = now - timedelta(minutes=minutes_ago)
            pattern = simulator.pick_pattern(fraud_rate)
            for event in simulator.generate_events(account, ts, pattern):
                if event[4] <= now:
                    planned.append((event[4], account, event, pattern is not None))

        planned.sort(key=lambda item: item[0])
        fraud_txn_ids = set()
        for i, (_, account, (amount, merchant, lat, lng, ts), is_fraud) in enumerate(planned, 1):
            account.refresh_from_db()
            txn = simulator._make_txn(account, amount, merchant, lat, lng, ts)
            # Scored inline (not .delay) so the history is deterministic and complete
            score_transaction(txn.id)
            if is_fraud:
                fraud_txn_ids.add(txn.id)
            if i % 100 == 0:
                self.stdout.write(f"  scored {i}/{len(planned)}")
        return fraud_txn_ids

    def _resolve_history(self, fraud_txn_ids, analysts):
        """Resolve most alerts older than ~5h so the queue looks like a working day."""
        cutoff = timezone.now() - timedelta(hours=5)
        old = Alert.objects.filter(status=Alert.Status.PENDING, created_at__lte=timezone.now())
        old = old.select_related("transaction", "risk_score")
        for alert in old:
            if alert.transaction.timestamp > cutoff or random.random() > 0.7:
                continue
            is_fraud = alert.transaction_id in fraud_txn_ids
            reject = random.random() < (0.8 if is_fraud else 0.15)
            decision = "rejected" if reject else "approved"
            analyst = random.choice(analysts)
            resolved_at = alert.transaction.timestamp + timedelta(minutes=random.randint(3, 55))
            notes = random.choice(
                ["Confirmed with cardholder; card blocked.", "Pattern matches card testing.",
                 "Merchant on watchlist.", "Cardholder unreachable; blocked as precaution."]
                if reject else
                ["Cardholder confirmed travel.", "Known large purchase.", "Verified via 3DS challenge."]
            )
            with db_transaction.atomic():
                previous = alert.status
                alert.status = Alert.Status.REJECTED if reject else Alert.Status.APPROVED
                alert.assigned_to = analyst
                alert.notes = notes
                alert.resolved_at = resolved_at
                alert.save(update_fields=["status", "assigned_to", "notes", "resolved_at"])
                AuditLog.objects.create(
                    actor=analyst,
                    action=f"alert_{decision}",
                    target=f"Alert:{alert.id}",
                    payload={
                        "previous_status": previous,
                        "new_status": alert.status,
                        "decision": decision,
                        "notes": notes,
                        "transaction_id": alert.transaction_id,
                        "idempotency_key": alert.transaction.idempotency_key,
                        "amount": str(alert.transaction.amount),
                        "composite_score": alert.risk_score.composite_score,
                        "seeded": True,
                    },
                )
