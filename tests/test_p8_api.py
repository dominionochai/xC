"""Offline contract and replay tests for the xC API."""
import importlib
import json
import os
import unittest

APP_IMPORT_ERROR = None
APP_IMPORT_WORKED = None
app = None
try:
    from backend.app import app
    APP_IMPORT_WORKED = "from backend.app import app"
except Exception as first_error:
    try:
        from backend.app import create_app
        app = create_app()
        APP_IMPORT_WORKED = "from backend.app import create_app"
    except Exception as fallback_error:
        APP_IMPORT_ERROR = f"app import: {first_error!r}; create_app fallback: {fallback_error!r}"

try:
    resume_module = importlib.import_module("backend.src.api.resume")
    RESUME_IMPORT_ERROR = None
except Exception as exc:
    resume_module, RESUME_IMPORT_ERROR = None, repr(exc)
try:
    events_module = importlib.import_module("backend.src.api.events")
    EVENTS_IMPORT_ERROR = None
except Exception as exc:
    events_module, EVENTS_IMPORT_ERROR = None, repr(exc)
try:
    from fastapi.testclient import TestClient
    TESTCLIENT_IMPORT_ERROR = None
except Exception as exc:
    TestClient, TESTCLIENT_IMPORT_ERROR = None, repr(exc)


def parse_sse(text):
    parsed = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if ":" in line and not line.startswith(":"):
                key, value = line.split(":", 1)
                fields[key] = value.lstrip()
        if "data" in fields:
            parsed.append({"id": fields.get("id"), "event": fields.get("event"),
                           "data": json.loads(fields["data"])})
    return parsed


class ApiContractTests(unittest.TestCase):
    def setUp(self):
        self._old_token = os.environ.get("XC_API_TOKEN")
        self.addCleanup(self._restore_token)
        os.environ["XC_API_TOKEN"] = "test-token"
        self.assertIsNone(APP_IMPORT_ERROR, f"{APP_IMPORT_WORKED}: {APP_IMPORT_ERROR}")
        self.assertIsNotNone(APP_IMPORT_WORKED, "neither app import nor create_app worked")
        self.assertIsNone(TESTCLIENT_IMPORT_ERROR, f"FastAPI TestClient import failed: {TESTCLIENT_IMPORT_ERROR}")
        self.assertIsNone(RESUME_IMPORT_ERROR, f"resume import failed: {RESUME_IMPORT_ERROR}")
        self.assertIsNone(EVENTS_IMPORT_ERROR, f"events import failed: {EVENTS_IMPORT_ERROR}")
        try:
            self.client = TestClient(app)
        except Exception as exc:
            self.fail(f"TestClient could not wrap app ({APP_IMPORT_WORKED}): {exc!r}")

    def _restore_token(self):
        if self._old_token is None:
            os.environ.pop("XC_API_TOKEN", None)
        else:
            os.environ["XC_API_TOKEN"] = self._old_token

    def tearDown(self):
        self._restore_token()

    @property
    def auth(self):
        return {"Authorization": "Bearer test-token"}

    def make_run(self):
        response = self.client.post("/api/v1/generate", headers=self.auth, json={})
        self.assertEqual(response.status_code, 202, f"generate: {response.status_code} {response.text}")
        return response.json()["run_id"]

    def test_health_is_public(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200, f"{response.status_code}: {response.text}")

    def test_presets_requires_configured_bearer(self):
        for headers in ({}, {"Authorization": "Bearer wrong-token"}):
            response = self.client.get("/api/v1/presets", headers=headers)
            self.assertEqual(response.status_code, 401, f"{response.status_code}: {response.text}")
            self.assertIn("detail", response.json(), response.text)

    def test_missing_token_configuration_is_503(self):
        os.environ.pop("XC_API_TOKEN", None)
        response = self.client.get("/api/v1/presets")
        self.assertEqual(response.status_code, 503, f"{response.status_code}: {response.text}")
        self.assertIn("missing_configuration", json.dumps(response.json()), response.text)

    def test_all_requested_routes_exist(self):
        run_id = self.make_run()
        cases = [
            ("GET", "/api/v1/presets", None),
            ("POST", "/api/v1/resolve", {"preset_id": "porsche-aime-leon-dore"}),
            ("POST", "/api/v1/reports", {}),
            ("GET", "/api/v1/reports", None),
            ("POST", "/api/v1/generate", {}),
            ("GET", "/api/v1/generate/stream?run_id=" + run_id, None),
            ("POST", "/api/v1/cancel", {"run_id": run_id}),
            ("GET", "/api/v1/memo.md", None),
            ("GET", "/api/v1/memo.pdf", None),
        ]
        for method, path, body in cases:
            response = self.client.request(method, path, headers=self.auth, json=body)
            self.assertNotEqual(response.status_code, 404,
                                f"{method} {path} returned 404: {response.text}")

    def test_report_without_preset_id_is_accepted_or_validated_without_requiring_it(self):
        response = self.client.post("/api/v1/reports", headers=self.auth, json={})
        self.assertIn(response.status_code, (201, 422), f"{response.status_code}: {response.text}")
        if response.status_code == 422:
            detail = response.text.casefold()
            self.assertFalse("preset_id" in detail and "required" in detail,
                             f"preset_id must be optional: {response.text}")

    def test_stream_has_gapless_ids_and_terminal_event_order(self):
        run_id = self.make_run()
        response = self.client.get("/api/v1/generate/stream", params={"run_id": run_id},
                                   headers=self.auth, timeout=3)
        self.assertEqual(response.status_code, 200, f"{response.status_code}: {response.text}")
        events = parse_sse(response.text)
        self.assertTrue(events, f"stream had zero data events; raw text: {response.text!r}")
        seqs = [item["data"]["seq"] for item in events]
        self.assertEqual(seqs[0], 1, f"event sequence must start at 1: {events!r}")
        self.assertEqual(seqs, list(range(1, len(seqs) + 1)), f"sequence gap: {events!r}")
        for item in events:
            self.assertEqual(int(item["id"]), item["data"]["seq"], f"SSE id mismatch: {item!r}")
        names = [item["event"] for item in events]
        self.assertGreaterEqual(len(names), 2, f"missing terminal events: {response.text!r}")
        self.assertEqual(names[-2:], ["report.completed", "run.finished"],
                         f"wrong final events: {names!r}; raw text: {response.text!r}")

    def test_resume_after_early_event_replays_gaplessly_without_duplicates(self):
        run_id = self.make_run()
        cancelled = self.client.post("/api/v1/cancel", headers=self.auth, json={"run_id": run_id})
        self.assertEqual(cancelled.status_code, 202, f"{cancelled.status_code}: {cancelled.text}")
        url = "/api/v1/generate/stream"
        initial_response = self.client.get(url, params={"run_id": run_id}, headers=self.auth, timeout=3)
        self.assertEqual(initial_response.status_code, 200, initial_response.text)
        initial = parse_sse(initial_response.text)
        self.assertGreaterEqual(len(initial), 3, f"expected several events: {initial_response.text!r}")
        cursor = initial[0]["data"]["seq"]
        resumed_response = self.client.get(url, params={"run_id": run_id},
                                           headers={**self.auth, "Last-Event-ID": str(cursor)}, timeout=3)
        self.assertEqual(resumed_response.status_code, 200, resumed_response.text)
        replay = parse_sse(resumed_response.text)
        seqs = [item["data"]["seq"] for item in replay]
        self.assertTrue(seqs and all(seq > cursor for seq in seqs), f"bad replay: {replay!r}")
        self.assertEqual(seqs, list(range(cursor + 1, cursor + 1 + len(seqs))), f"replay gap: {replay!r}")
        self.assertEqual(len(seqs), len(set(seqs)), f"duplicate replay IDs: {replay!r}")

    def test_invalid_resume_cursor_reports_run_not_resumable(self):
        run_id = self.make_run()
        response = self.client.get("/api/v1/generate/stream", params={"run_id": run_id},
                                   headers={**self.auth, "Last-Event-ID": "999999"}, timeout=3)
        body = response.text
        event_names = [item["event"] for item in parse_sse(body)] if response.status_code == 200 else []
        self.assertTrue("RUN_NOT_RESUMABLE" in body or "RUN_NOT_RESUMABLE" in event_names or
                        response.status_code in (404, 409),
                        f"expected RUN_NOT_RESUMABLE or HTTP 404/409, got {response.status_code}: {body}")

    def test_cancel_returns_202(self):
        run_id = self.make_run()
        response = self.client.post("/api/v1/cancel", headers=self.auth, json={"run_id": run_id})
        self.assertEqual(response.status_code, 202, f"{response.status_code}: {response.text}")

    def test_client_credentials_never_appear_in_resolve_or_report_responses(self):
        secrets = {"qloo_api_key": "LEAKED", "QLOO_API_KEY": "LEAKED", "api_key": "LEAKED"}
        resolve = self.client.post("/api/v1/resolve", headers=self.auth,
                                   json={"preset_id": "porsche-aime-leon-dore", **secrets})
        self.assertNotIn("LEAKED", resolve.text, f"credential leaked by resolve: {resolve.text}")
        report = self.client.post("/api/v1/reports", headers=self.auth,
                                  json={"content": secrets, **secrets})
        self.assertNotIn("LEAKED", report.text, f"credential leaked by reports: {report.text}")


class DirectModuleTests(ApiContractTests):
    def test_replay_buffer_retains_exactly_newest_capacity(self):
        self.assertTrue(hasattr(resume_module, "REPLAY_BUFFER_SIZE"), "missing REPLAY_BUFFER_SIZE")
        size = resume_module.REPLAY_BUFFER_SIZE
        self.assertEqual(size, 5000)
        buffer = resume_module.EventReplayBuffer(capacity=size)
        for index in range(size + 10):
            buffer.append("tick", {"index": index})
        retained = buffer.snapshot()
        self.assertEqual(len(retained), size)
        seqs = [event["seq"] for event in retained]
        self.assertEqual(seqs, list(range(11, size + 11)))

    def test_sse_encoder_matches_wire_format_and_preserves_payload(self):
        payload = {"text": "offline ✓", "count": 3}
        envelope = events_module.event_envelope(7, "sample.event", payload)
        encoded = events_module.encode_sse("sample.event", envelope)
        self.assertTrue(encoded.endswith("\n\n"), repr(encoded))
        lines = encoded.splitlines()
        self.assertEqual(lines[:2], ["id: 7", "event: sample.event"], repr(encoded))
        self.assertTrue(lines[2].startswith("data: "), repr(encoded))
        decoded = json.loads(lines[2][6:])
        self.assertEqual(decoded, envelope)
        self.assertEqual(decoded["data"], payload)


if __name__ == "__main__":
    unittest.main()
