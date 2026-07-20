#!/usr/bin/env python3
"""Guards the LLM safety-gate parsing/threshold logic in run_command_hardware.

Run:  python3 tests/test_hardware_safety_gate.py   (exit 0 = ok)

Mocks the OpenAI client so this needs no network/API key. Checks: a
low-harm verdict lets the score through, a high-harm verdict is rejected,
and any parse/API failure fails CLOSED (no execution) — never silently
allowed, since a real device is on the other end.
"""
import os
import sys
from unittest.mock import MagicMock, patch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import critleayer.tools_hardware_safety as gate  # noqa: E402


def _mock_response(text: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock(message=MagicMock(content=text))]
    return resp


def test_low_harm_score_parses_and_passes():
    with patch.object(gate, "OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_response(
            "SCORE: 1\nREASON: read-only ping, no risk."
        )
        score, reason = gate._llm_harm_score("ping -c1 10.0.19.35")
    assert score == 1
    assert "no risk" in reason.lower()
    assert score <= gate._MAX_ALLOWED_HARM_SCORE


def test_high_harm_score_parses_and_blocks():
    with patch.object(gate, "OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_response(
            "SCORE: 9\nREASON: flood/DoS against a live relay."
        )
        score, reason = gate._llm_harm_score("hping3 --flood 10.0.19.35")
    assert score == 9
    assert score > gate._MAX_ALLOWED_HARM_SCORE


def test_unparseable_response_fails_closed():
    with patch.object(gate, "OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_response(
            "I'm not sure, this could be risky."
        )
        score, reason = gate._llm_harm_score("nmap -sV 10.0.19.35")
    assert score is None  # caller must treat None as "do not execute"


def test_api_failure_fails_closed():
    with patch.object(gate, "OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.side_effect = RuntimeError("network down")
        score, reason = gate._llm_harm_score("ping 10.0.19.35")
    assert score is None
    assert "network down" in reason


def test_uses_main_agents_model_and_provider_via_env():
    """ot_agent.py exports CRITBENCH_SAFETY_* right after resolving its own
    model/provider — the safety gate must use exactly that, not a fixed
    model, so it judges with whatever model the run is actually evaluating."""
    env = {
        "CRITBENCH_SAFETY_MODEL": "kit.qwen3.5-397b-A17b",
        "CRITBENCH_SAFETY_BASE_URL": "https://ki-toolbox.scc.kit.edu/api/v1",
        "CRITBENCH_SAFETY_API_KEY_ENV": "KITOOLBOX_API_KEY",
        "KITOOLBOX_API_KEY": "test-key-123",
    }
    with patch.dict(os.environ, env, clear=False), patch.object(gate, "OpenAI") as MockClient:
        MockClient.return_value.chat.completions.create.return_value = _mock_response(
            "SCORE: 1\nREASON: fine."
        )
        gate._llm_harm_score("ping -c1 10.0.19.35")

    MockClient.assert_called_once_with(
        base_url="https://ki-toolbox.scc.kit.edu/api/v1", api_key="test-key-123",
    )
    _, kwargs = MockClient.return_value.chat.completions.create.call_args
    assert kwargs["model"] == "kit.qwen3.5-397b-A17b"


def test_falls_back_when_env_not_set():
    """No ot_agent.py in this process (standalone/test use) → plain OpenAI
    default endpoint with the fallback model, not a crash."""
    scrub = ("CRITBENCH_SAFETY_MODEL", "CRITBENCH_SAFETY_BASE_URL", "CRITBENCH_SAFETY_API_KEY_ENV")
    env = {k: os.environ[k] for k in scrub if k in os.environ}
    for k in scrub:
        os.environ.pop(k, None)
    try:
        with patch.object(gate, "OpenAI") as MockClient:
            MockClient.return_value.chat.completions.create.return_value = _mock_response(
                "SCORE: 1\nREASON: fine."
            )
            gate._llm_harm_score("ping -c1 10.0.19.35")
        MockClient.assert_called_once_with(base_url=None, api_key=gate.os.environ.get("OPENAI_API_KEY") or "not-needed")
        _, kwargs = MockClient.return_value.chat.completions.create.call_args
        assert kwargs["model"] == gate._FALLBACK_SAFETY_MODEL
    finally:
        os.environ.update(env)


if __name__ == "__main__":
    test_low_harm_score_parses_and_passes()
    test_high_harm_score_parses_and_blocks()
    test_unparseable_response_fails_closed()
    test_api_failure_fails_closed()
    test_uses_main_agents_model_and_provider_via_env()
    test_falls_back_when_env_not_set()
    print("OK — hardware safety-gate parsing/threshold logic verified")
