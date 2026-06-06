-- Requires base schema first (tickets table).
-- For a fresh Hack AI project, run supabase/hack_ai_bootstrap.sql instead of this file alone.

CREATE TABLE IF NOT EXISTS public.ticket_hypotheses (
  ticket_id UUID PRIMARY KEY REFERENCES public.tickets(id) ON DELETE CASCADE,
  hypotheses JSONB NOT NULL DEFAULT '[]',
  selected_index INTEGER NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.ticket_hypotheses TO anon, authenticated;
ALTER TABLE public.ticket_hypotheses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read hypotheses" ON public.ticket_hypotheses;
DROP POLICY IF EXISTS "Public write hypotheses" ON public.ticket_hypotheses;
DROP POLICY IF EXISTS "Public update hypotheses" ON public.ticket_hypotheses;
CREATE POLICY "Public read hypotheses" ON public.ticket_hypotheses FOR SELECT USING (true);
CREATE POLICY "Public write hypotheses" ON public.ticket_hypotheses FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update hypotheses" ON public.ticket_hypotheses FOR UPDATE USING (true);

DO $realtime$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.ticket_hypotheses;
EXCEPTION WHEN duplicate_object THEN NULL; END $realtime$;
