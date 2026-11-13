-- Existing V2 only. Re-runnable, data-preserving. No reset, no DROP.
BEGIN;
ALTER TABLE public.t_block
  ADD COLUMN IF NOT EXISTS question_groups JSONB NOT NULL DEFAULT '[]'::jsonb;
COMMIT;
