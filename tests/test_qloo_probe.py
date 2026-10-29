"""Offline tests for the bounded Qloo discovery probe."""

import json
from pathlib import Path

from backend.qloo import QlooClient
from scripts import qloo_probe


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "synthetic"


def _offline_client():
    transport = qloo_probe._SyntheticTransport()
    client = QlooClient(
        "synthetic-never-a-real-key",
        transport=transport,
        retries=0,
        pacing_seconds=0,
        cache_ttl=0,
        call_budget=2,
    )
    return client, transport


def test_selftest_cli_uses_checked_in_fixtures_and_stays_offline(capsys):
    """The CLI selftest must work from a clean checkout without credentials."""
    assert (FIXTURES / "search_response.json").is_file()
    assert (FIXTURES / "insights_response.json").is_file()

    assert qloo_probe.main(["--selftest"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_probe_exercises_only_the_known_synthetic_get_routes():
    client, transport = _offline_client()

    report = qloo_probe.run_probe(client)

    assert len(transport.paths) == 2
    assert any(p.endswith("/search") for p in transport.paths)
    assert any(p.endswith("/v2/insights") for p in transport.paths)
    assert report["network_attempts"] == 2
    assert set(report["answers"]) == {f"P{i}" for i in range(1, 14)}
    assert report["answers"]["P1"]["status"] == "observed"
    assert report["answers"]["P5"]["status"] == "observed"
    assert report["answers"]["P13"]["status"] == "not_tested"
    assert "synthetic-never-a-real-key" not in json.dumps(client.call_log)


def test_redaction_covers_credential_fields_and_secret_values():
    secret = "synthetic-never-a-real-key"
    redacted = qloo_probe._redact(
        {
            "api_key": secret,
            "Authorization": "Bearer " + secret,
            "message": "credential=" + secret,
        },
        secret,
    )

    encoded = json.dumps(redacted)
    assert secret not in encoded
    assert "[REDACTED]" in encoded
