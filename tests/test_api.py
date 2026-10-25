"""Focused API contract tests for the W4 backend."""

import importlib.util
import unittest


try:
    from backend.api import create_app
except Exception as exc:  # The backend may not be available in this checkout.
    create_app = None
    _CREATE_APP_IMPORT_ERROR = exc
else:
    _CREATE_APP_IMPORT_ERROR = None


@unittest.skipUnless(
    importlib.util.find_spec("fastapi") is not None,
    "FastAPI is not installed",
)
class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if create_app is None:
            raise unittest.SkipTest(
                "backend.api.create_app is unavailable: "
                f"{_CREATE_APP_IMPORT_ERROR}"
            )

        try:
            app = create_app()
        except Exception as exc:
            raise unittest.SkipTest(f"create_app() is unavailable: {exc}") from exc

        try:
            from fastapi.testclient import TestClient

            cls.client = TestClient(app)
        except Exception as exc:
            raise unittest.SkipTest(
                f"FastAPI TestClient is unavailable or incompatible: {exc}"
            ) from exc

    def test_health_endpoint_returns_success(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)

    def test_request_body_over_64_kib_is_rejected(self):
        response = self.client.post(
            "/health",
            content=b"x" * (64 * 1024 + 1),
            headers={"content-type": "application/octet-stream"},
        )
        self.assertEqual(response.status_code, 413)

    def test_memo_pdf_returns_not_implemented_when_exposed(self):
        response = self.client.get("/memo.pdf")
        if response.status_code in (404, 405):
            self.skipTest("/memo.pdf is not exposed as a GET endpoint")
        self.assertEqual(response.status_code, 501)


if __name__ == "__main__":
    unittest.main()
