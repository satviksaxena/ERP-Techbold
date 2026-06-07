from unittest.mock import MagicMock

from app.store.supabase_store import SupabaseStore


def test_insert_command_strips_internal_metadata():
    store = SupabaseStore.__new__(SupabaseStore)
    store.client = MagicMock()
    store.client.table.return_value.insert.return_value.execute.return_value.data = [{"id": "cmd-1"}]

    store.insert_command(
        "ticket-uuid",
        agent_name="Customer System Analyzer",
        command_text="df -h",
        script_diff="+ test",
        safety_status="Safe",
        human_status="Pending",
        output_logs="",
        plan_intent="diagnostic",
        _path_source="runbook_path",
        from_path_switch="1",
    )

    payload = store.client.table.return_value.insert.call_args[0][0]
    assert payload["command_text"] == "df -h"
    assert "plan_intent" not in payload
    assert "_path_source" not in payload
    assert "from_path_switch" not in payload
