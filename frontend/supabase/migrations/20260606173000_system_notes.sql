ALTER TABLE public.system_info
  ADD COLUMN IF NOT EXISTS system_notes TEXT NOT NULL DEFAULT '';
