#!/bin/sh
set -e

echo "Waiting for database..."
# Simple retry loop — Postgres may still be starting
i=0
until python -c "
import asyncio, asyncpg, os, sys
async def main():
    url = os.environ['DATABASE_URL'].replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(url)
    await conn.close()
asyncio.run(main())
" 2>/dev/null; do
  i=$((i + 1))
  if [ "$i" -ge 30 ]; then
    echo "Database not ready after 60s" >&2
    exit 1
  fi
  sleep 2
done

echo "Running migrations..."
alembic upgrade head

echo "Starting API..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers "${UVICORN_WORKERS:-2}"
