-- ONE-TIME CONFIGURATION AFTER DEPLOYING THE APP TO A PERSISTENT HOST.
-- Set up Supabase Vault secrets with the dashboard, not literal passwords in this SQL.
-- Secret names: unfounded_api_base_url = https://your-host.example (NO trailing /)
--               unfounded_worker_secret = random 32+ characters
-- Requires pg_cron, pg_net, vault extensions installed in the project.
CREATE EXTENSION IF NOT EXISTS pg_cron;
CREATE EXTENSION IF NOT EXISTS pg_net;

CREATE SCHEMA IF NOT EXISTS ut_private;
REVOKE ALL ON SCHEMA ut_private FROM PUBLIC;

CREATE OR REPLACE FUNCTION ut_private.trigger_newsroom(endpoint text)
RETURNS bigint LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE
  base text;
  secret text;
  request_id bigint;
BEGIN
  SELECT decrypted_secret INTO base FROM vault.decrypted_secrets
  WHERE name = 'unfounded_api_base_url' LIMIT 1;
  SELECT decrypted_secret INTO secret FROM vault.decrypted_secrets
  WHERE name = 'unfounded_worker_secret' LIMIT 1;
  IF base IS NULL OR secret IS NULL OR endpoint NOT IN
    ('/jobs/discover','/jobs/prepare','/jobs/reschedule','/jobs/publish') THEN
    RAISE EXCEPTION 'Newsroom secrets or endpoint not configured';
  END IF;
  SELECT net.http_post(
      url := trim(trailing '/' from base) || endpoint,
      headers := jsonb_build_object('Content-Type','application/json','x-worker-secret',secret),
      body := '{}'::jsonb,
      timeout_milliseconds := 25000
  ) INTO request_id;
  RETURN request_id;
END $$;
REVOKE ALL ON FUNCTION ut_private.trigger_newsroom(text) FROM PUBLIC;

-- All times below are UTC, not WIB (Asia/Jakarta).
-- 00:00, 08:00, 16:00 WIB = 17:00 (prev day), 01:00 and 09:00 UTC.
SELECT cron.schedule('unfounded-discover', '0 1,9,17 * * *',
  $$SELECT ut_private.trigger_newsroom('/jobs/discover')$$);
SELECT cron.schedule('unfounded-prepare', '15 1,9,17 * * *',
  $$SELECT ut_private.trigger_newsroom('/jobs/prepare')$$);
SELECT cron.schedule('unfounded-reschedule', '*/15 * * * *',
  $$SELECT ut_private.trigger_newsroom('/jobs/reschedule')$$);
-- Publish job checks at most one due approved post per run; first checks at 06/12/18 WIB.
SELECT cron.schedule('unfounded-publish', '*/5 * * * *',
  $$SELECT ut_private.trigger_newsroom('/jobs/publish')$$);
