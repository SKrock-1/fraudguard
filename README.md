# FraudGuard

Real-Time Fraud Detection Engine with Django, Celery, and Channels.

See [fraud-detection-project-plan.md](fraud-detection-project-plan.md) for the design.

## Local development

```bash
uv sync --extra dev
cp .env.example .env
uv run python manage.py migrate
uv run pytest
```

With `CELERY_TASK_ALWAYS_EAGER=True` (the default) scoring runs inline, so no
Redis or worker is needed for the test suite.

### Analyst dashboard

The Next.js console lives in [dashboard/](dashboard/README.md). To run the
whole thing locally with no Redis server, put these in `.env` (see
`.env.example`): `REDIS_URL=fakeredis://`, `CHANNEL_LAYERS_BACKEND=inmemory`,
`CELERY_TASK_ALWAYS_EAGER=True`, and a `DEMO_PASSWORD`. Then:

```bash
uv run python manage.py migrate
uv run python manage.py seed_demo          # demo users + 24h of scored history
uv run daphne -b 127.0.0.1 -p 8000 fraudguard.asgi:application
cd dashboard && npm install && npm run dev
```

Sign in at http://localhost:3000 as `maya.chen`. The sidebar's
**Simulate traffic** button streams synthetic transactions through the real
scoring pipeline, so alerts arrive live over the WebSocket.

## Running the full stack (Docker)

```bash
docker compose up --build
curl "http://localhost:8000/api/health/?worker=1"
```

This starts Postgres, Redis, and one app container that runs both Daphne and a
Celery worker via [start.sh](start.sh). `?worker=1` makes the health check ping
the worker too, so a 200 means web, database, Redis and worker are all up.

## Deployment (free tier)

| Piece | Provider |
|---|---|
| Web + Celery worker (one container) | Render free web service ([render.yaml](render.yaml)) |
| Postgres | Neon |
| Redis | Upstash (`rediss://` URL) |

1. Create a Neon database and an Upstash Redis instance.
2. In Render, create a Blueprint from this repo (it reads `render.yaml`).
3. Set `DATABASE_URL`, `REDIS_URL`, `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
   in the service's environment. See [.env.example](.env.example) for formats.
4. Render runs migrations on every start and health-checks `/api/health/`.

**Free-tier tradeoff:** the worker shares a container with the web server because
Render's free plan has no background-worker service type. If either process
dies, `start.sh` stops the container so Render restarts it. In real production the
worker would be a separate, independently scaled service. The free service also
sleeps when idle, so the first request after a pause is slow.
