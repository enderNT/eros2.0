#!/usr/bin/env sh
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 USER_ID" >&2
  exit 2
fi

USER_ID="$1"
DB_SERVICE="${DB_SERVICE:-llm-logs-db}"
DB_USER="${DB_USER:-agente}"
DB_NAME="${DB_NAME:-agente_logs}"

docker compose exec -T "$DB_SERVICE" psql -U "$DB_USER" -d "$DB_NAME" -v ON_ERROR_STOP=1 \
  -v user_id="$USER_ID" <<'SQL'
SELECT set_config('app.user_id_to_clear', :'user_id', false);
DO $$
BEGIN
  IF to_regclass('public.conversation_summaries') IS NOT NULL THEN
    DELETE FROM public.conversation_summaries WHERE user_id = current_setting('app.user_id_to_clear');
  END IF;
  IF to_regclass('public.historial') IS NOT NULL THEN
    DELETE FROM public.historial WHERE user_id = current_setting('app.user_id_to_clear');
  END IF;
  IF to_regclass('public.perfil') IS NOT NULL THEN
    DELETE FROM public.perfil WHERE user_id = current_setting('app.user_id_to_clear');
  END IF;
END $$;
SQL

echo "Memory cleared for user: $USER_ID"
