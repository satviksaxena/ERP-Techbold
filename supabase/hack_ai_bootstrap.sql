-- =============================================================================
-- Hack AI (cpobgjkowqlqmogmuelk) — run this ENTIRE script in SQL Editor → Run
-- Do NOT run ticket_hypotheses alone first — tickets must exist before it.
-- Safe to re-run: uses IF NOT EXISTS / DROP POLICY IF EXISTS.
-- =============================================================================

-- 1. Core tables (order matters — foreign keys)
CREATE TABLE IF NOT EXISTS public.tickets (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  customer_name TEXT NOT NULL,
  priority TEXT NOT NULL DEFAULT 'Medium',
  status TEXT NOT NULL DEFAULT 'Open',
  report_text TEXT NOT NULL DEFAULT '',
  active_agent TEXT NOT NULL DEFAULT 'Problem Analyzer',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.system_info (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID NOT NULL REFERENCES public.tickets(id) ON DELETE CASCADE,
  host_ip TEXT NOT NULL,
  username TEXT NOT NULL,
  port INTEGER NOT NULL DEFAULT 22,
  os_version TEXT NOT NULL,
  connection_status TEXT NOT NULL DEFAULT 'Idle',
  system_notes TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.ai_commands (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID NOT NULL REFERENCES public.tickets(id) ON DELETE CASCADE,
  agent_name TEXT NOT NULL,
  command_text TEXT NOT NULL,
  script_diff TEXT NOT NULL DEFAULT '',
  safety_status TEXT NOT NULL DEFAULT 'Safe',
  human_status TEXT NOT NULL DEFAULT 'Pending',
  output_logs TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.activities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID NOT NULL UNIQUE REFERENCES public.tickets(id) ON DELETE CASCADE,
  summary TEXT NOT NULL DEFAULT '',
  root_cause TEXT NOT NULL DEFAULT '',
  actions_taken TEXT NOT NULL DEFAULT '',
  commands_summary TEXT NOT NULL DEFAULT '',
  validation_result TEXT NOT NULL DEFAULT '',
  submitted_to_erp BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.ticket_hypotheses (
  ticket_id UUID PRIMARY KEY REFERENCES public.tickets(id) ON DELETE CASCADE,
  hypotheses JSONB NOT NULL DEFAULT '[]',
  selected_index INTEGER NOT NULL DEFAULT 0,
  reasoning_summary TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE public.ticket_hypotheses
  ADD COLUMN IF NOT EXISTS reasoning_summary TEXT NOT NULL DEFAULT '';

-- 2. Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON public.tickets TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.system_info TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ai_commands TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.activities TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ticket_hypotheses TO anon, authenticated;
GRANT ALL ON public.tickets, public.system_info, public.ai_commands, public.activities, public.ticket_hypotheses TO service_role;

-- 3. Row Level Security
ALTER TABLE public.tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_info ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ticket_hypotheses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Public read tickets" ON public.tickets;
DROP POLICY IF EXISTS "Public write tickets" ON public.tickets;
DROP POLICY IF EXISTS "Public update tickets" ON public.tickets;
DROP POLICY IF EXISTS "Public delete tickets" ON public.tickets;
CREATE POLICY "Public read tickets" ON public.tickets FOR SELECT USING (true);
CREATE POLICY "Public write tickets" ON public.tickets FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update tickets" ON public.tickets FOR UPDATE USING (true);
CREATE POLICY "Public delete tickets" ON public.tickets FOR DELETE USING (true);

DROP POLICY IF EXISTS "Public read sysinfo" ON public.system_info;
DROP POLICY IF EXISTS "Public write sysinfo" ON public.system_info;
DROP POLICY IF EXISTS "Public update sysinfo" ON public.system_info;
DROP POLICY IF EXISTS "Public delete sysinfo" ON public.system_info;
CREATE POLICY "Public read sysinfo" ON public.system_info FOR SELECT USING (true);
CREATE POLICY "Public write sysinfo" ON public.system_info FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update sysinfo" ON public.system_info FOR UPDATE USING (true);
CREATE POLICY "Public delete sysinfo" ON public.system_info FOR DELETE USING (true);

DROP POLICY IF EXISTS "Public read cmds" ON public.ai_commands;
DROP POLICY IF EXISTS "Public write cmds" ON public.ai_commands;
DROP POLICY IF EXISTS "Public update cmds" ON public.ai_commands;
DROP POLICY IF EXISTS "Public delete cmds" ON public.ai_commands;
CREATE POLICY "Public read cmds" ON public.ai_commands FOR SELECT USING (true);
CREATE POLICY "Public write cmds" ON public.ai_commands FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update cmds" ON public.ai_commands FOR UPDATE USING (true);
CREATE POLICY "Public delete cmds" ON public.ai_commands FOR DELETE USING (true);

DROP POLICY IF EXISTS "Public read acts" ON public.activities;
DROP POLICY IF EXISTS "Public write acts" ON public.activities;
DROP POLICY IF EXISTS "Public update acts" ON public.activities;
DROP POLICY IF EXISTS "Public delete acts" ON public.activities;
CREATE POLICY "Public read acts" ON public.activities FOR SELECT USING (true);
CREATE POLICY "Public write acts" ON public.activities FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update acts" ON public.activities FOR UPDATE USING (true);
CREATE POLICY "Public delete acts" ON public.activities FOR DELETE USING (true);

DROP POLICY IF EXISTS "Public read hypotheses" ON public.ticket_hypotheses;
DROP POLICY IF EXISTS "Public write hypotheses" ON public.ticket_hypotheses;
DROP POLICY IF EXISTS "Public update hypotheses" ON public.ticket_hypotheses;
CREATE POLICY "Public read hypotheses" ON public.ticket_hypotheses FOR SELECT USING (true);
CREATE POLICY "Public write hypotheses" ON public.ticket_hypotheses FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update hypotheses" ON public.ticket_hypotheses FOR UPDATE USING (true);

-- 4. Realtime (ignore if already added)
DO $realtime$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.tickets;
EXCEPTION WHEN duplicate_object THEN NULL; END $realtime$;
DO $realtime$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.system_info;
EXCEPTION WHEN duplicate_object THEN NULL; END $realtime$;
DO $realtime$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.ai_commands;
EXCEPTION WHEN duplicate_object THEN NULL; END $realtime$;
DO $realtime$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.activities;
EXCEPTION WHEN duplicate_object THEN NULL; END $realtime$;
DO $realtime$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE public.ticket_hypotheses;
EXCEPTION WHEN duplicate_object THEN NULL; END $realtime$;

-- 5. Verify (should return 5 table names)
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
