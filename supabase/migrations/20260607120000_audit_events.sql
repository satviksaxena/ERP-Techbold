-- Persistent audit trail for jury scoring (category C).
CREATE TABLE IF NOT EXISTS public.audit_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID REFERENCES public.tickets(id) ON DELETE CASCADE,
  action TEXT NOT NULL,
  details JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS audit_events_ticket_id_created_at_idx
  ON public.audit_events (ticket_id, created_at);

GRANT SELECT, INSERT, DELETE ON public.audit_events TO anon, authenticated;
GRANT ALL ON public.audit_events TO service_role;

ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read audit" ON public.audit_events;
DROP POLICY IF EXISTS "Public write audit" ON public.audit_events;
DROP POLICY IF EXISTS "Public delete audit" ON public.audit_events;
CREATE POLICY "Public read audit" ON public.audit_events FOR SELECT USING (true);
CREATE POLICY "Public write audit" ON public.audit_events FOR INSERT WITH CHECK (true);
CREATE POLICY "Public delete audit" ON public.audit_events FOR DELETE USING (true);

ALTER PUBLICATION supabase_realtime ADD TABLE public.audit_events;
