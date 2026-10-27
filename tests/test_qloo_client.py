"""Offline, deterministic tests for the Qloo HTTP client."""
import unittest

from backend.qloo import (
    CallBudgetExceeded,
    QlooClient,
    QlooHTTPError,
    TransportResponse,
)


class FakeTransport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, params, headers, timeout):
        self.calls.append({
            "url": url,
            "params": dict(params),
            "headers": dict(headers),
            "timeout": timeout,
        })
        if not self.responses:
            raise AssertionError("unexpected transport call")
        return self.responses.pop(0)


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


def response(status=200, headers=None, body=b'{"results":[]}'):
    return TransportResponse(status, headers or {}, body)


class QlooClientTests(unittest.TestCase):
    def test_api_key_is_sent_only_as_header_not_in_urls_logs_or_errors(self):
        secret = "test-secret-never-log"
        transport = FakeTransport([response(status=401)])
        client = QlooClient(secret, transport=transport, retries=0, pacing_seconds=0)

        with self.assertRaises(QlooHTTPError) as raised:
            client.get("/search", {"query": "offline"})

        self.assertEqual(transport.calls[0]["headers"]["X-Api-Key"], secret)
        self.assertNotIn(secret, transport.calls[0]["url"])
        self.assertNotIn(secret, str(client.call_log))
        self.assertNotIn(secret, str(raised.exception))

    def test_pacing_uses_injected_clock_and_sleep(self):
        clock = FakeClock()
        transport = FakeTransport([
            response(body=b'{"results":[{"id":"one"}]}'),
            response(body=b'{"results":[{"id":"two"}]}'),
        ])
        client = QlooClient(
            "offline-key",
            transport=transport,
            retries=0,
            pacing_seconds=0.5,
            cache_ttl=0,
            sleep=clock.sleep,
            clock=clock,
        )

        client.get("/search", {"query": "one"})
        client.get("/search", {"query": "two"})

        self.assertEqual(clock.sleeps, [0.5])
        self.assertEqual(len(transport.calls), 2)

    def test_retry_honors_retry_after_header(self):
        clock = FakeClock()
        transport = FakeTransport([
            response(429, {"Retry-After": "1.25"}, b'{"error":"slow down"}'),
            response(body=b'{"results":[]}'),
        ])
        client = QlooClient(
            "offline-key",
            transport=transport,
            retries=1,
            pacing_seconds=0,
            sleep=clock.sleep,
            clock=clock,
        )

        self.assertEqual(client.get("/search", {"query": "retry"}), {"results": []})
        self.assertEqual(clock.sleeps, [1.25])
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(client.call_log[0]["retry_after_seconds"], 1.25)

    def test_call_budget_exhaustion_raises_named_exception(self):
        transport = FakeTransport([response(), response()])
        client = QlooClient(
            "offline-key",
            transport=transport,
            retries=0,
            pacing_seconds=0,
            call_budget=1,
            cache_ttl=0,
        )

        client.get("/search", {"query": "first"})
        with self.assertRaises(CallBudgetExceeded):
            client.get("/search", {"query": "second"})

        self.assertEqual(client.calls_used, 1)
        self.assertEqual(len(transport.calls), 1)

    def test_cache_hit_does_not_make_a_second_transport_call(self):
        transport = FakeTransport([response(body=b'{"results":[{"id":"one"}]}')])
        client = QlooClient(
            "offline-key",
            transport=transport,
            retries=0,
            pacing_seconds=0,
            cache_ttl=60,
        )

        first = client.get("/search", {"query": "same"})
        second = client.get("/search", {"query": "same"})

        self.assertEqual(first, {"results": [{"id": "one"}]})
        self.assertEqual(second, first)
        self.assertEqual(len(transport.calls), 1)
        self.assertTrue(client.call_log[-1]["cached"])


if __name__ == "__main__":
    unittest.main()
