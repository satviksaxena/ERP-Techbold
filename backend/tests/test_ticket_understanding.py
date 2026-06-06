"""Tests for Gemini thinking response parsing and ticket understanding config."""
from __future__ import annotations

from types import SimpleNamespace

from app.agent.ticket_understanding import parse_thinking_response


def test_parse_thinking_response_splits_thought_and_answer():
    response = SimpleNamespace(
        text='{"hypotheses": []}',
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text="Symptom suggests nginx upstream failure.", thought=True),
                        SimpleNamespace(text="Also check disk space.", thought=True),
                        SimpleNamespace(
                            text='{"hypotheses": [{"title": "Service down"}]}',
                            thought=False,
                        ),
                    ]
                )
            )
        ],
    )

    reasoning, answer = parse_thinking_response(response)

    assert "nginx upstream" in reasoning
    assert "disk space" in reasoning
    assert "Service down" in answer


def test_parse_thinking_response_falls_back_to_response_text():
    response = SimpleNamespace(
        text='{"hypotheses": [{"title": "Permissions"}]}',
        candidates=[],
    )

    reasoning, answer = parse_thinking_response(response)

    assert reasoning == ""
    assert "Permissions" in answer
