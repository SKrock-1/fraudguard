# FraudGuard — Research Plan, PRD, and Build Prompt

Companion to the system design doc. This one is for *before* and *during* the build: what to research first, what the product actually commits to, and a ready-to-use prompt for an AI coding agent (Claude Code or similar) to build it phase by phase.

---

# Part 1 — Research Plan

Do this before writing application code. Each row is a spike, not a rabbit hole — timebox it.

| # | Research question | Why it matters | Method | Output |
|---|---|---|---|---|
| R1 | How do real systems structure rule-based fraud checks (velocity, geo-velocity, amount anomaly)? | You're implementing simplified versions — worth knowing what the real pattern looks like so yours isn't naive | Read public engineering write-ups (Stripe Radar, PayPal fraud engineering blog posts) | Short notes doc: 3-5 rule patterns worth implementing |
| R2 | Which free dataset actually supports which part of the pipeline? | Kaggle CC Fraud lacks account/geo fields; PaySim has time-steps but no geo | Load each dataset, inspect schema/columns directly | A table: dataset → usable for (ML training / velocity testing / geo testing) |
| R3 | Rule-based vs. supervised vs. unsupervised scoring — what fits an MVP? | Fraud data is heavily imbalanced (often <1% positive); naive supervised models will look "accurate" while being useless | Prototype Isolation Forest and Logistic Regression on the Kaggle dataset in a notebook, compare precision/recall | Chosen model + a one-paragraph justification you can say out loud in an interview |
| R4 | How to handle severe class imbalance? | Directly affects whether your precision/recall numbers mean anything | Read about class weighting and SMOTE, try one on your prototype | A decision: which imbalance technique you're using and why |
| R5 | Celery task design: single task vs. chain vs. chord for the scoring pipeline? | Determines whether rule engine and ML scorer run sequentially or in parallel and get combined | Read Celery canvas docs, sketch both designs | Chosen task graph, sketched in your own notes |
| R6 | What does "insert-only" actually require at the Postgres level? | App-level checks aren't enough — you want a DB-enforced guarantee | Read Postgres `REVOKE`/`GRANT` docs, test it manually in `psql` | A working `REVOKE UPDATE, DELETE` statement you've verified actually blocks a Django `.save()` on an existing row |
| R7 | Current free-tier limits for Neon, Upstash, Render, Vercel | These change — don't build against limits from memory | Check each provider's current pricing/limits page directly before you commit to the architecture | Confirmed limits noted in the deployment section |
| R8 | What's the minimum viable "explainability" for a risk score? | A bare number ("0.83") is not defensible in an interview or in a real system | Look at how contributing-factors fields are typically structured (JSON of rule_name → contribution) | Your `RiskScore.factors` JSON shape, decided before you write the model |

---

# Part 2 — Product Requirements Document (PRD)

## 2.1 Problem statement

Financial platforms need to catch suspicious transactions fast enough to act, with a defensible trail of who decided what and why. Most portfolio projects either skip the "fast enough" part (batch-only) or the "defensible trail" part (no audit design). FraudGuard does both, at a scope one person can actually ship.

## 2.2 Goals

- Ingest transactions with strict idempotency (no duplicate processing on retry)
- Score every transaction for risk within a few seconds, combining deterministic rules and an ML model
- Push flagged transactions to an analyst in real time, not on a refresh
- Give every human decision a permanent, tamper-resistant record
- Prove the scoring actually works, with backtested precision/recall against labeled data — not just "it runs"

## 2.3 Non-goals (v1)

- Real payment processor integration (synthetic/historical data only)
- Multi-tenant SaaS support
- Horizontal scaling / true production infra (the deployment is free-tier and openly scoped as a demo, not a scale target)
- Model retraining automation beyond a manually-triggered batch job

## 2.4 Personas

| Persona | Needs |
|---|---|
| **Analyst** | See new alerts instantly, understand *why* something was flagged, resolve it with one action |
| **Admin** | Manage rule thresholds, see system-wide metrics, audit any decision |
| **Upstream system / API client** | Submit a transaction once and trust it won't be double-processed on retry, get a fast ack |

## 2.5 User stories

- As an **API client**, I submit a transaction and get an immediate acknowledgment, even if my request is retried due to a network timeout.
- As an **analyst**, I see a new alert appear on my dashboard within seconds of a risky transaction occurring, with the specific factors that triggered it.
- As an **analyst**, I approve or reject an alert, and that decision is permanently recorded and cannot be silently altered later — by me or anyone else.
- As an **admin**, I can see aggregate precision/recall against a backtest dataset to know whether the scoring is actually working.

## 2.6 Functional requirements

| ID | Requirement |
|---|---|
| FR-1 | `POST /api/transactions/` accepts a transaction with a required `idempotency_key`; duplicate keys return the original record, not a new one |
| FR-2 | Every accepted transaction is scored asynchronously — the ingestion request never waits on scoring |
| FR-3 | The rule engine evaluates velocity, geo-velocity, and amount-anomaly checks per transaction |
| FR-4 | The ML scorer produces an anomaly score using a model trained offline and loaded once per worker process |
| FR-5 | Rule and ML outputs combine into one composite `RiskScore`, stored with a JSON breakdown of contributing factors |
| FR-6 | Scores above threshold create an `Alert` and broadcast it to connected analysts over WebSocket within the same request cycle that created it |
| FR-7 | Analysts can approve/reject an alert via API; the decision updates the alert and writes an `AuditLog` entry |
| FR-8 | The `AuditLog` table is insert-only at the database level, not just the application level |
| FR-9 | Three roles exist — `ingestion_client`, `analyst`, `admin` — enforced on every endpoint |
| FR-10 | Ingestion is rate-limited per API client |
| FR-11 | A backtesting script replays a labeled dataset through the full scoring path and reports precision/recall/F1 |

## 2.7 Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Ingestion ack latency | < 200ms (excludes scoring) |
| NFR-2 | End-to-end alert latency (transaction created → alert visible on dashboard) | < 5s on free-tier infra |
| NFR-3 | Test coverage on rule engine and serializers | > 80% |
| NFR-4 | Ingestion throughput, verified via load test | Sustain at least 20-50 req/s without error-rate spikes (numbers depend on free-tier compute — record what you actually measure) |
| NFR-5 | Backtest performance | Recall and precision numbers must be recorded and reproducible from a script, not eyeballed |
| NFR-6 | Secrets handling | No credentials in source control; all via environment variables |

## 2.8 Success metrics

- Backtest precision/recall/F1 on a labeled dataset, with the actual numbers written down
- Measured p95 ingestion latency and alert latency under Locust load
- Zero successful mutation of an existing `AuditLog` row in a test that explicitly attempts one

## 2.9 Assumptions & constraints

- Single developer, part-time alongside coursework/internship
- Free-tier infrastructure throughout — performance numbers are demo-scale, and that's stated openly rather than implied as production-scale
- Data is historical/synthetic; no live financial integration or real user funds involved

## 2.10 Risks & mitigations

| Risk | Mitigation |
|---|---|
| Free-tier Postgres/Redis/web service limits get hit mid-build | Confirm current limits before committing (see R7); design the combined web+worker container from day one rather than retrofitting it |
| ML model looks "accurate" but is useless on imbalanced data | Backtest with precision/recall/F1, not raw accuracy, from the start (R3, R4) |
| Scope creep toward multi-tenancy / real payments | Explicit non-goals section above — refer back to it when tempted |

## 2.11 Milestones

Matches the 9-phase roadmap in the system design doc — roughly one phase per week, ~8-9 weeks total.

---

# Part 3 — Detailed Build Prompt

Use this as the actual prompt for an AI coding agent (Claude Code, etc.). It's written to be handed over phase by phase — paste Phase 1, let it build and show you output, review, then move to Phase 2. Don't paste the whole thing at once; each phase should be reviewed before the next starts.

```
You are building FraudGuard, a production-style Django backend for real-time
financial fraud detection. Work in phases. After each phase: run the tests you
wrote, show me the output, and wait for my go-ahead before starting the next
phase. Do not skip ahead.

GLOBAL STACK
- Django 5.x, Django REST Framework
- PostgreSQL (psycopg2-binary)
- Celery + Redis as broker
- Django Channels + channels-redis for WebSockets
- djangorestframework-simplejwt for auth
- scikit-learn + joblib for the ML scorer
- pytest-django, factory-boy for testing
- Locust for load testing (separate, later)

GLOBAL CONVENTIONS
- Every model gets a factory-boy factory in a `factories.py` alongside it.
- Every view/endpoint gets at least one happy-path and one failure-path test.
- Use CELERY_TASK_ALWAYS_EAGER=True in the test settings so tests don't need a
  live broker.
- Composite risk scores must store a JSON breakdown of contributing factors,
  never just a bare number.

---
PHASE 1 — Foundation
Create a Django project `fraudguard` with apps: `accounts`, `transactions`,
`risk`, `alerts`, `audit`.

Models:
- accounts.Account: user FK, avg_spend (decimal), spend_stddev (decimal),
  last_known_lat/lng, last_transaction_at.
- transactions.Transaction: account FK, amount, currency, merchant, lat, lng,
  timestamp, idempotency_key (unique), status (pending/scored).

Build:
- POST /api/transactions/ — requires idempotency_key. If it already exists,
  return the existing record with 200, not a new one. Otherwise create with
  status=pending and return 202.
- JWT auth via simplejwt. Role field on the user model:
  ingestion_client / analyst / admin.

Acceptance criteria:
- Posting the same idempotency_key twice results in exactly one Transaction
  row in the database, verified by a test.
- Unauthenticated requests are rejected.

---
PHASE 2 — Rule engine (synchronous, no Celery yet)
In `risk/rules.py`, implement as plain functions (not yet Celery tasks):
- velocity_check(account, window_minutes, max_count) — count transactions in
  the window; use a Redis sorted set keyed by account id, not a DB query.
- impossible_travel_check(account, transaction) — distance between
  last_known location and this transaction's location, divided by elapsed
  time; flag if it implies an unrealistic travel speed.
- amount_anomaly_check(account, transaction) — z-score of this amount
  against the account's rolling avg/stddev.

Each function returns (triggered: bool, detail: dict) so results are
explainable, not just booleans.

Acceptance criteria:
- Each rule has a test with a clearly fraudulent input and a clearly benign
  input, asserting the correct triggered value.

---
PHASE 3 — Async pipeline
Introduce Celery with Redis as broker. Move the three rule checks into a
single Celery task `score_transaction(transaction_id)` triggered on
transaction creation. Add retry with backoff on transient failures (e.g.
Redis connection errors), max 3 retries.

Acceptance criteria:
- With CELERY_TASK_ALWAYS_EAGER=True, a test asserts that creating a
  transaction results in a RiskScore row being created without any
  additional manual trigger.

---
PHASE 4 — ML scoring
Write an offline training script (`risk/train_model.py`, run manually, not
part of the request path) that trains an Isolation Forest on the Kaggle
Credit Card Fraud dataset (or PaySim) and serializes it with joblib.

In the Celery worker, load the model once at process start (module-level,
not inside the task function). Add `ml_score(transaction)` to the scoring
task, combine with rule engine output into one composite score stored on
risk.RiskScore, with a `factors` JSONField breaking down what contributed
(each triggered rule + the ML score).

Acceptance criteria:
- A test with a mocked model asserts the composite score combines both
  rule and ML contributions, and that `factors` is populated.

---
PHASE 5 — Real-time alert layer
Add Django Channels with channels-redis as the layer. Build an
AlertConsumer that joins an "analysts" group on connect (auth required —
only analyst/admin roles may connect). When a RiskScore exceeds threshold,
create an alerts.Alert row and group_send it to the "analysts" group.

Acceptance criteria:
- Using Channels' WebsocketCommunicator, a test creates a high-risk
  transaction and asserts a message is received on a connected consumer.

---
PHASE 6 — Review workflow + audit
Build POST /api/alerts/{id}/review/ accepting approve/reject, restricted to
analyst/admin roles. On review, update the Alert and write an audit.AuditLog
row (actor, action, target, payload, timestamp).

At the database level, revoke UPDATE and DELETE on the audit_log table from
the app's DB role (write this as a migration using RunSQL, not just a
comment).

Acceptance criteria:
- A test attempts to update an existing AuditLog row directly and asserts
  it fails at the database level (not just via application logic).

---
PHASE 7 — Hardening
Add per-API-client throttling on the ingestion endpoint using a custom
DRF throttle class. Add indexes on Transaction (account_id, timestamp) and
Transaction.idempotency_key (already unique, confirm it's indexed).
Enforce RBAC on every endpoint explicitly — write a test per role per
endpoint asserting correct allow/deny.

Acceptance criteria:
- A role-matrix test file exists covering every endpoint × every role.

---
PHASE 8 — Backtesting + load test
Write `scripts/backtest.py`: replay a labeled dataset through the full
scoring path (rules + ML) and print precision/recall/F1 against the known
labels. Write a Locust file simulating concurrent POSTs to the ingestion
endpoint.

Acceptance criteria:
- Running the backtest script produces actual numbers, printed to stdout,
  not just "done."
- Running Locust against a local server produces a request/latency report.

---
PHASE 9 — Deployment prep
Write a startup script that launches both the ASGI server (daphne/uvicorn)
and a Celery worker as two processes in one container, for deployment to a
single free Render web service. Document required environment variables
(DATABASE_URL for Neon, REDIS_URL for Upstash, JWT secret, etc.) in a
.env.example file. Do not commit real secrets.

Acceptance criteria:
- The startup script runs both processes locally via Docker Compose and
  both are confirmed alive (web responds to a health check, worker log
  shows it's consumed a task).
```

---

Next natural step: hand Phase 1 of the prompt above to your coding agent of choice and start from there.
