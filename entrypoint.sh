#!/bin/sh
set -e

# Wait for PostgreSQL to be ready (with timeout)
echo "Waiting for PostgreSQL to be ready..."
MAX_RETRIES=30
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  if PGPASSWORD=${PGPASSWORD:-postgres} psql -h ${PGHOST:-db} -U ${PGUSER:-postgres} -c '\q' 2>/dev/null; then
    echo "PostgreSQL is up - executing command"
    break
  fi
  
  RETRY_COUNT=$((RETRY_COUNT+1))
  echo "Waiting for PostgreSQL to be ready... ($RETRY_COUNT/$MAX_RETRIES)"
  sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
  echo "PostgreSQL did not become ready in time, but continuing anyway..."
fi

# Execute the command passed to docker
exec "$@"