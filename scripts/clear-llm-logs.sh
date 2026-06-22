#!/usr/bin/env sh
set -eu

DB_SERVICE="${DB_SERVICE:-llm-logs-db}"
DB_USER="${DB_USER:-agente}"
DB_NAME="${DB_NAME:-agente_logs}"

docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF to_regclass('public.llm_calls') IS NOT NULL THEN
    TRUNCATE TABLE public.llm_calls RESTART IDENTITY;
  END IF;
END $$;
SQL

echo "LLM logs cleared."
