"""Offline unit tests for backend.robustness."""

import json
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import backend.robustness as robustness


class SanitizeNameTests(unittest.TestCase):
    def test_removes_controls_and_trims_whitespace(self):
        self.assertEqual(robustness.sanitize_name(" \tAc\x00me\x7f Corp\n "), "Acme Corp")

    def test_rejects_empty_and_overlong_names(self):
        with self.assertRaises(ValueError):
            robustness.sanitize_name(" \x00\n ")
        with self.assertRaises(ValueError):
            robustness.sanitize_name("x" * 121)

    def test_accepts_bounds(self):
        self.assertEqual(robustness.sanitize_name("x"), "x")
        self.assertEqual(robustness.sanitize_name("x" * 120), "x" * 120)


class ResolveWithRobustnessTests(unittest.TestCase):
    def _use_resolver(self, resolver):
        return patch.object(
            robustness.importlib,
            "import_module",
            side_effect=lambda path: SimpleNamespace(run=resolver)
            if path == "backend.src.engine.resolve"
            else ImportError(path),
        )

    def test_unknown_brand_returns_error_and_suggestions(self):
        qloo = SimpleNamespace(search=lambda query: [{"name": "Acme"}, {"name": "Acme Labs"}])
        resolver = lambda qloo, budget, query: {"status": "not_found", "candidates": []}
        with self._use_resolver(resolver):
            result = robustness.resolve_with_robustness(qloo, 5, "Unknown")
        self.assertEqual(result, {
            "status": "not_found",
            "error": "unknown brand",
            "suggestions": ["Acme", "Acme Labs"],
        })

    def test_ambiguity_returns_candidates(self):
        candidates = [{"name": "Acme North"}, {"name": "Acme South"}]
        qloo = SimpleNamespace(search=lambda query: [])
        resolver = lambda qloo, budget, query: {"status": "ok", "candidates": candidates}
        with self._use_resolver(resolver):
            result = robustness.resolve_with_robustness(qloo, 5, "Acme")
        self.assertEqual(result["status"], "ambiguous")
        self.assertEqual(result["candidates"], candidates)

    def test_transient_failure_retries_and_returns_partial_without_raising(self):
        calls = []
        delays = []

        def resolver(qloo, budget, query):
            calls.append(query)
            raise RuntimeError("temporary qloo outage")

        qloo = SimpleNamespace(search=lambda query: [])
        with self._use_resolver(resolver):
            result = robustness.resolve_with_robustness(
                qloo, 5, "Acme", sleep_fn=delays.append
            )
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [0.1, 0.2])
        self.assertEqual(result, {
            "status": "partial",
            "warnings": ["qloo_transient_failure:2 retries"],
        })


class CacheTests(unittest.TestCase):
    def test_disabled_cache_does_not_store(self):
        cache = robustness.Cache()
        cache.set("key", "value")
        self.assertIsNone(cache.get("key"))

    def test_enabled_cache_respects_ttl(self):
        cache = robustness.Cache(enabled=True)
        cache.set("key", {"value": 1}, ttl_seconds=1)
        self.assertEqual(cache.get("key"), {"value": 1})
        cache.set("short", "value", ttl_seconds=0.01)
        time.sleep(0.02)
        self.assertIsNone(cache.get("short"))


class RunLimiterTests(unittest.TestCase):
    def test_limit_and_release(self):
        limiter = robustness.RunLimiter(max_runs=3)
        self.assertTrue(limiter.acquire())
        self.assertTrue(limiter.acquire())
        self.assertTrue(limiter.acquire())
        self.assertFalse(limiter.acquire())
        limiter.release()
        self.assertTrue(limiter.acquire())


class SafeLoggerTests(unittest.TestCase):
    def test_emits_json_lines_and_redacts_credentials(self):
        lines = []
        logger = robustness.SafeLogger(sink=lines.append)
        logger.info("request", api_key="should-not-appear", detail="sk-abc123")
        payload = json.loads(lines[0])
        self.assertEqual(payload["level"], "info")
        self.assertEqual(payload["message"], "request")
        self.assertEqual(payload["api_key"], "[REDACTED]")
        self.assertEqual(payload["detail"], "[REDACTED]")


if __name__ == "__main__":
    unittest.main()
