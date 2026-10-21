ALTER TABLE public.drafts ADD COLUMN IF NOT EXISTS post_format varchar(20) NOT NULL DEFAULT 'single';
ALTER TABLE public.drafts ADD COLUMN IF NOT EXISTS carousel_slides jsonb NOT NULL DEFAULT '[]'::jsonb;
