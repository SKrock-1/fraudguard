import json

from django.core.management.base import BaseCommand

from risk.retraining import retrain


class Command(BaseCommand):
    help = "Retrain the ML anomaly model from analyst-labelled alerts (champion/challenger)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Evaluate only; save nothing.")
        parser.add_argument("--force", action="store_true", help="Promote even if the challenger does not beat the champion.")

    def handle(self, *args, **opts):
        result = retrain(trigger="manual", force=opts["force"], dry_run=opts["dry_run"])
        self.stdout.write(json.dumps(result, indent=2))
