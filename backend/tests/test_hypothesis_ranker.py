from app.agent.hypothesis_ranker import rerank_hypotheses


def test_rerank_boosts_matching_service_path():
    hypotheses = [
        {
            "title": "Service not enabled on boot",
            "likely_root_cause": "systemd unit disabled",
            "confidence": "medium",
        },
        {
            "title": "Disk full",
            "likely_root_cause": "storage exhaustion",
            "confidence": "medium",
        },
    ]
    evidence = {"failed_units": ["customer-status.service"], "disabled_units": []}
    updated = rerank_hypotheses(hypotheses, evidence, selected_index=0)
    assert updated[0]["confidence"] == "high"
