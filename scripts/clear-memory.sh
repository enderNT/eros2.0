#!/usr/bin/env sh
set -eu

DB_SERVICE="${DB_SERVICE:-llm-logs-db}"
DB_USER="${DB_USER:-agente}"
DB_NAME="${DB_NAME:-agente_logs}"

docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 <<'SQL'
DO $$
BEGIN
  IF to_regclass('public.conversation_summaries') IS NOT NULL THEN
    TRUNCATE TABLE public.conversation_summaries RESTART IDENTITY;
  END IF;
  IF to_regclass('public.historial') IS NOT NULL THEN
    TRUNCATE TABLE public.historial RESTART IDENTITY;
  END IF;
  IF to_regclass('public.perfil') IS NOT NULL THEN
    TRUNCATE TABLE public.perfil RESTART IDENTITY;
  END IF;
END $$;
SQL

echo "All memory tables cleared."
