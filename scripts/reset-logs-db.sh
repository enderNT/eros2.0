#!/usr/bin/env sh
set -eu

DB_SERVICE="${DB_SERVICE:-llm-logs-db}"
DB_USER="${DB_USER:-agente}"
DB_NAME="${DB_NAME:-agente_logs}"

docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
DROP SCHEMA IF EXISTS public CASCADE;
CREATE SCHEMA public;
GRANT ALL ON SCHEMA public TO agente;
GRANT ALL ON SCHEMA public TO public;
SQL

echo "Postgres database schema reset."
