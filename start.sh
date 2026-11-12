#!/usr/bin/env bash
# Runs the ASGI server (Daphne) and a Celery worker as two processes in one
# container. Render's free plan has no background-worker service type, so both
# live in the single free web service. In real production these would be
# separate, independently scaled services.
#
# If either process dies, the other is stopped and the container exits non-zero
# so the platform restarts it, rather than serving HTTP with no worker behind it.
set -euo pipefail

python manage.py migrate --noinput

celery -A fraudguard worker \
    --loglevel="${CELERY_LOG_LEVEL:-info}" \
    --concurrency="${CELERY_CONCURRENCY:-2}" &
worker_pid=$!

daphne -b 0.0.0.0 -p "${PORT:-8000}" fraudguard.asgi:application &
web_pid=$!

shutdown() {
    kill -TERM "$web_pid" "$worker_pid" 2>/dev/null || true
}
trap shutdown TERM INT

set +e
wait -n "$web_pid" "$worker_pid"
exit_code=$?
echo "start.sh: a process exited (code $exit_code); stopping the other" >&2
shutdown
wait
exit "$exit_code"
