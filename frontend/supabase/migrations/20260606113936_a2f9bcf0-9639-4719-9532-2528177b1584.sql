
CREATE TABLE public.tickets (
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

CREATE TABLE public.system_info (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ticket_id UUID NOT NULL REFERENCES public.tickets(id) ON DELETE CASCADE,
  host_ip TEXT NOT NULL,
  username TEXT NOT NULL,
  port INTEGER NOT NULL DEFAULT 22,
  os_version TEXT NOT NULL,
  connection_status TEXT NOT NULL DEFAULT 'Idle',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE public.ai_commands (
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

CREATE TABLE public.activities (
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

GRANT SELECT, INSERT, UPDATE, DELETE ON public.tickets TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.system_info TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.ai_commands TO anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.activities TO anon, authenticated;
GRANT ALL ON public.tickets, public.system_info, public.ai_commands, public.activities TO service_role;

ALTER TABLE public.tickets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.system_info ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_commands ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.activities ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read tickets" ON public.tickets FOR SELECT USING (true);
CREATE POLICY "Public write tickets" ON public.tickets FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update tickets" ON public.tickets FOR UPDATE USING (true);
CREATE POLICY "Public delete tickets" ON public.tickets FOR DELETE USING (true);

CREATE POLICY "Public read sysinfo" ON public.system_info FOR SELECT USING (true);
CREATE POLICY "Public write sysinfo" ON public.system_info FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update sysinfo" ON public.system_info FOR UPDATE USING (true);
CREATE POLICY "Public delete sysinfo" ON public.system_info FOR DELETE USING (true);

CREATE POLICY "Public read cmds" ON public.ai_commands FOR SELECT USING (true);
CREATE POLICY "Public write cmds" ON public.ai_commands FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update cmds" ON public.ai_commands FOR UPDATE USING (true);
CREATE POLICY "Public delete cmds" ON public.ai_commands FOR DELETE USING (true);

CREATE POLICY "Public read acts" ON public.activities FOR SELECT USING (true);
CREATE POLICY "Public write acts" ON public.activities FOR INSERT WITH CHECK (true);
CREATE POLICY "Public update acts" ON public.activities FOR UPDATE USING (true);
CREATE POLICY "Public delete acts" ON public.activities FOR DELETE USING (true);

ALTER PUBLICATION supabase_realtime ADD TABLE public.tickets;
ALTER PUBLICATION supabase_realtime ADD TABLE public.ai_commands;
ALTER PUBLICATION supabase_realtime ADD TABLE public.activities;
ALTER PUBLICATION supabase_realtime ADD TABLE public.system_info;
