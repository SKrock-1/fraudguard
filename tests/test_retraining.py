"""
Retraining from analyst labels: dataset building, champion/challenger
promotion, hot-swap into the scoring pipeline, API permissions and audit.
"""
import io
from decimal import Decimal

import joblib
import numpy as np
import pytest
from sklearn.ensemble import IsolationForest

import risk.tasks as tasks
from accounts.factories import AccountFactory
from alerts.models import Alert
from audit.models import AuditLog
from risk.models import ModelVersion, RiskScore
from risk.retraining import build_dataset, retrain
from transactions.factories import TransactionFactory
from transactions.models import Transaction


def _scored(account, features, alert_status=None, score=0.2):
    txn = TransactionFactory(account=account, amount=Decimal(str(round(features[0], 2))), status=Transaction.Status.SCORED)
    rs = RiskScore.objects.create(
        transaction=txn, composite_score=score, model_version="test", factors={"ml_features": list(features)},
    )
    if alert_status:
        Alert.objects.create(transaction=txn, risk_score=rs, status=alert_status)
    return txn


@pytest.fixture
def labelled_history(db):
    """120 normal transactions, 10 confirmed fraud, 6 approved alerts, 3 pending."""
    rng = np.random.default_rng(7)
    account = AccountFactory()
    for _ in range(120):
        amt = float(rng.uniform(10, 150))
        _scored(account, [amt, float(rng.integers(9, 21)), float(rng.integers(0, 5)), amt / 81.0, float(rng.normal(0, 0.8))])
    for _ in range(10):
        amt = float(rng.uniform(2500, 6000))
        _scored(account, [amt, float(rng.integers(0, 5)), 6.0, amt / 81.0, float(rng.uniform(6, 12))], Alert.Status.REJECTED, 0.9)
    for _ in range(6):
        amt = float(rng.uniform(150, 300))
        _scored(account, [amt, 14.0, 2.0, amt / 81.0, 2.5], Alert.Status.APPROVED, 0.65)
    for _ in range(3):
        _scored(account, [999.0, 3.0, 6.0, 12.0, 5.0], Alert.Status.PENDING, 0.7)
    return account


@pytest.fixture
def model_path(tmp_path, settings):
    path = tmp_path / "isolation_forest.joblib"
    settings.ML_MODEL_PATH = str(path)
    settings.RETRAIN_MIN_SAMPLES = 50
    settings.RETRAIN_MIN_FRAUD_LABELS = 5
    return path


@pytest.fixture(autouse=True)
def restore_model():
    saved = (tasks.ML_MODEL, tasks.ML_MODEL_VERSION, dict(tasks._MODEL_FILE_STATE))
    tasks.ML_MODEL, tasks.ML_MODEL_VERSION = None, "none"
    yield
    tasks.ML_MODEL, tasks.ML_MODEL_VERSION = saved[0], saved[1]
    tasks._MODEL_FILE_STATE.update(saved[2])


def _weak_champion(path):
    """A baseline file trained on noise, which any sensible challenger should beat."""
    rng = np.random.default_rng(0)
    weak = IsolationForest(n_estimators=10, random_state=0).fit(rng.uniform(0, 10000, size=(200, 5)))
    joblib.dump({"model": weak, "model_version": "weak-champion"}, path)
    tasks._MODEL_FILE_STATE["key"] = ("stale", 0)  # make refresh_model() notice the new file


class TestDataset:
    def test_labels_come_from_analyst_decisions(self, labelled_history):
        X, y, human = build_dataset()
        assert X.shape == (136, 5)  # pending alerts are excluded
        assert int(y.sum()) == 10
        assert int(human.sum()) == 16  # 10 fraud + 6 approved
        assert int(((y == 0) & ~human).sum()) == 120


class TestRetrain:
    def test_skips_without_enough_fraud_labels(self, db, model_path):
        account = AccountFactory()
        for i in range(60):
            _scored(account, [50.0 + i, 12.0, 2.0, 1.0, 0.0])
        result = retrain()
        assert result["status"] == "skipped"
        assert not ModelVersion.objects.exists()

    def test_promotes_when_there_is_no_champion(self, labelled_history, model_path):
        result = retrain()
        assert result["status"] == "promoted"
        assert not model_path.exists()  # the shipped baseline file is never overwritten
        run = ModelVersion.objects.get()
        bundle = joblib.load(io.BytesIO(bytes(run.artifact)))
        assert bundle["model_version"] == result["version"]
        assert tasks.ML_MODEL_VERSION == result["version"]
        run = ModelVersion.objects.get()
        assert run.promoted and run.labeled_fraud == 10 and run.labeled_legit == 6
        assert result["metrics"]["challenger"]["average_precision"] > 0.5

    def test_challenger_beats_weak_champion(self, labelled_history, model_path):
        _weak_champion(model_path)
        result = retrain()
        m = result["metrics"]
        assert m["champion_version"] == "weak-champion"
        assert m["challenger"]["average_precision"] >= m["champion"]["average_precision"]
        assert result["status"] == "promoted"

    def test_keeps_champion_when_challenger_is_worse(self, labelled_history, model_path, monkeypatch):
        champion_version = retrain()["version"]  # strong champion
        import risk.retraining as rt
        real_fit = rt._fit
        noise = np.random.default_rng(1).uniform(0, 10000, size=(200, 5))
        monkeypatch.setattr(rt, "_fit", lambda X, c, r: real_fit(noise, c, r))
        result = retrain()
        assert result["version"] != champion_version
        assert result["status"] == "kept_champion"
        assert result["metrics"]["champion_version"] == champion_version
        assert tasks.ML_MODEL_VERSION == champion_version
        assert ModelVersion.objects.get(version=result["version"]).artifact is None
        assert ModelVersion.objects.filter(promoted=False).count() == 1

    def test_dry_run_saves_nothing(self, labelled_history, model_path):
        result = retrain(dry_run=True)
        assert result["status"] == "dry_run"
        assert not ModelVersion.objects.exists()

    def test_writes_audit_entry(self, labelled_history, model_path):
        result = retrain()
        entry = AuditLog.objects.get(target=f"Model:{result['version']}")
        assert entry.action == "model_promoted"
        assert entry.payload["labeled_fraud"] == 10

    def test_promoted_model_is_used_for_new_scores(self, labelled_history, model_path):
        result = retrain()
        txn = TransactionFactory(account=labelled_history, amount=Decimal("40.00"))
        tasks.score_transaction(txn.id)
        rs = RiskScore.objects.get(transaction=txn)
        assert rs.model_version == f"rules_v1+{result['version']}"
        assert len(rs.factors["ml_features"]) == 5


class TestApi:
    def test_admin_can_retrain(self, auth_admin_client, labelled_history, model_path):
        r = auth_admin_client.post("/api/ml/retrain/", {}, format="json")
        assert r.status_code == 200, r.data
        assert r.data["status"] == "promoted"
        assert ModelVersion.objects.get().created_by.username == "admin_super"

    def test_retrain_reports_insufficient_data(self, auth_admin_client, model_path):
        r = auth_admin_client.post("/api/ml/retrain/", {}, format="json")
        assert r.status_code == 422
        assert r.data["status"] == "skipped"

    def test_analyst_cannot_retrain(self, auth_analyst_client, model_path):
        assert auth_analyst_client.post("/api/ml/retrain/", {}, format="json").status_code == 403

    def test_ingestion_client_cannot_list_models(self, auth_ingestion_client):
        assert auth_ingestion_client.get("/api/ml/models/").status_code == 403

    def test_analyst_can_list_models(self, auth_analyst_client, labelled_history, model_path):
        retrain()
        r = auth_analyst_client.get("/api/ml/models/")
        assert r.status_code == 200
        assert r.data["production_version"] == r.data["runs"][0]["version"]


class TestModelPersistence:
    def test_new_process_loads_promoted_model_from_db(self, labelled_history, model_path):
        result = retrain()
        tasks.ML_MODEL, tasks.ML_MODEL_VERSION = None, "baseline"  # simulate a fresh process
        tasks.refresh_model(force=True)
        assert tasks.ML_MODEL_VERSION == result["version"]
        assert tasks.ML_MODEL is not None

    def test_corrupt_artifact_keeps_current_model(self, labelled_history, model_path):
        result = retrain()
        ModelVersion.objects.filter(version=result["version"]).update(artifact=b"not a model")
        sentinel = object()
        tasks.ML_MODEL, tasks.ML_MODEL_VERSION = sentinel, "baseline"
        tasks.refresh_model(force=True)
        assert tasks.ML_MODEL is sentinel
