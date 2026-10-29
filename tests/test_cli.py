"""Tests for the starter CLI."""

import io
import unittest
from contextlib import redirect_stdout

from xc.cli import main


class TestMain(unittest.TestCase):
    def test_echoes_arguments(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["hello", "world"])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "hello world\n")

    def test_shows_starter_message_without_arguments(self) -> None:
        output = io.StringIO()
        with redirect_stdout(output):
            status = main([])
        self.assertEqual(status, 0)
        self.assertEqual(output.getvalue(), "xC\n")


if __name__ == "__main__":
    unittest.main()
