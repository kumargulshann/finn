#!/bin/sh
# Single-container entrypoint: FastAPI on loopback, Next.js on the public $PORT.
# Next.js proxies /api/v1/* to the API (see frontend/next.config.ts rewrites).
set -e

DATA_DIR=/app/backend/data
mkdir -p "$DATA_DIR"
# First boot (or ephemeral disk): start from the pre-indexed snapshot.
if [ ! -f "$DATA_DIR/finn.db" ]; then
  cp /app/backend/seed/finn.db "$DATA_DIR/finn.db"
fi

cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

# Wait for the API so the first page load doesn't race startup migrations.
for i in $(seq 1 60); do
  python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')" 2>/dev/null && break
  sleep 1
done

cd /app/frontend
PORT="${PORT:-7860}" HOSTNAME=0.0.0.0 node server.js &
WEB_PID=$!

# Exit if either process dies so the platform restarts the container.
while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do sleep 5; done
exit 1
