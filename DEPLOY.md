# Deploying FraudGuard for free

| Piece | Service | Free tier notes |
|---|---|---|
| PostgreSQL | [Neon](https://neon.tech) | Permanent free tier, 0.5 GB |
| Redis (Celery broker, velocity counters, WebSocket layer) | [Upstash](https://upstash.com) | 500K commands/month, TLS only (`rediss://`) |
| Django API + Celery worker (one container) | [Render](https://render.com) | Sleeps after 15 min idle; first request takes ~50 s |
| Next.js dashboard | [Vercel](https://vercel.com) | No sleep |
| Weekly model retrain, CI | GitHub Actions | Free on public repos |

Sign in to each service with GitHub. Secrets (connection strings, passwords)
go only into the services' own settings pages, never into the repository.

## 1. Neon (PostgreSQL)

1. Create a project (any name, region closest to Render's, e.g. AWS Singapore or US East).
2. On the dashboard choose **Connect**, keep **Pooled connection** on, and copy the
   connection string. It looks like
   `postgresql://USER:PASSWORD@ep-xxx-pooler.REGION.aws.neon.tech/neondb?sslmode=require`.

## 2. Upstash (Redis)

1. Create a Redis database (free plan, same region family as Render). Keep TLS enabled.
2. Copy the **Redis URL** starting with `rediss://` (two s's).

## 3. Render (API + worker)

1. **New → Blueprint**, pick the `fraudguard` GitHub repository. Render reads `render.yaml`.
2. Fill the variables Render asks for:

   | Variable | Value |
   |---|---|
   | `DATABASE_URL` | the Neon connection string |
   | `REDIS_URL` | the Upstash `rediss://` URL |
   | `ALLOWED_HOSTS` | `fraudguard.onrender.com` (your service's hostname) |
   | `CSRF_TRUSTED_ORIGINS` | `https://fraudguard.onrender.com` |
   | `DEMO_PASSWORD` | a password of your choice for the demo logins |

3. Deploy. The first boot runs migrations and seeds the demo users and 24 h of
   scored traffic (`SEED_DEMO_ON_START`). Check `https://<service>.onrender.com/api/health/`
   returns `"status": "ok"`.

Demo logins (all use `DEMO_PASSWORD`): `maya.chen` and `dev.patel` (analysts),
`ops.admin` (admin), `ingest-gateway` (ingestion client).

## 4. Vercel (dashboard)

1. **Add New → Project**, import the repository, set **Root Directory** to `dashboard`.
2. Environment variables (Production):

   | Variable | Value |
   |---|---|
   | `BACKEND_URL` | `https://fraudguard.onrender.com` |
   | `NEXT_PUBLIC_WS_URL` | `wss://fraudguard.onrender.com` |

3. Deploy, then open the Vercel URL and sign in with a demo login. `BACKEND_URL`
   is read at build time, so redeploy after changing it.

## 5. GitHub Actions secrets (weekly retrain)

Repository **Settings → Secrets and variables → Actions → New repository secret**:

| Secret | Value |
|---|---|
| `FRAUDGUARD_API_URL` | `https://fraudguard.onrender.com` |
| `FRAUDGUARD_ADMIN_USERNAME` | `ops.admin` |
| `FRAUDGUARD_ADMIN_PASSWORD` | the `DEMO_PASSWORD` value |

Run **Actions → Weekly model retrain → Run workflow** once to check it. Without
the secrets the job skips itself instead of failing.

## Free-tier trade-offs

- Daphne and the Celery worker share one container because Render's free plan has
  no background-worker service. In production they would be separate, independently
  scaled services.
- Render's disk is wiped on every deploy. That is why retrained models are stored
  in the database (`ModelVersion.artifact`) rather than on disk.
- After 15 minutes without traffic the API sleeps; the dashboard shows
  "Reconnecting" until the first request wakes it. An UptimeRobot ping every
  10 minutes keeps it awake if needed.
