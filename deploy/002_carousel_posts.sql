-- Apply once before deploying carousel code; preserve all existing single drafts.
BEGIN;
ALTER TABLE public.drafts
  ADD COLUMN IF NOT EXISTS post_format varchar(12) NOT NULL DEFAULT 'single';
ALTER TABLE public.drafts
  ADD COLUMN IF NOT EXISTS carousel_slides jsonb NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE public.drafts
  ADD CONSTRAINT carousel_post_format_check CHECK (post_format IN ('single','carousel'));
COMMIT;
