-- Add multi-agent pipeline columns (safe to re-run)
ALTER TABLE public.ticket_hypotheses
  ADD COLUMN IF NOT EXISTS reasoning_summary TEXT NOT NULL DEFAULT '';

ALTER TABLE public.ticket_hypotheses
  ADD COLUMN IF NOT EXISTS pipeline_state JSONB NOT NULL DEFAULT '{}';

ALTER TABLE public.ai_commands
  ADD COLUMN IF NOT EXISTS agent_reasoning TEXT NOT NULL DEFAULT '';
