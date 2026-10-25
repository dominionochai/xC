"""Unit tests for the documented agents.events EventBus API."""

import unittest

from agents.events import EventBus


class EventBusTests(unittest.TestCase):
    def test_sequence_starts_at_one_and_increments(self):
        bus = EventBus()

        first = bus.emit("started", {"step": 1})
        second = bus.emit("progress", {"step": 2})

        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)
        self.assertEqual([event["seq"] for event in bus.get_run_events()], [1, 2])

    def test_buffer_retains_last_5000_events(self):
        bus = EventBus()
        for index in range(5002):
            bus.emit("tick", {"index": index})

        events = bus.get_run_events()

        self.assertEqual(len(events), 5000)
        self.assertEqual(events[0]["seq"], 3)
        self.assertEqual(events[-1]["seq"], 5002)

    def test_large_payload_preview_is_limited_to_two_kibibytes(self):
        bus = EventBus()

        event = bus.emit("large", {"value": "x" * 10000})
        preview = event["payload_preview"]

        self.assertIsInstance(preview, str)
        self.assertLessEqual(len(preview.encode("utf-8")), 2 * 1024)

    def test_keepalive_emits_comment_and_cancellation_stops_generator(self):
        bus = EventBus()
        comments = bus.keepalive_comments(interval_s=0.05)

        self.assertEqual(next(comments), ": keepalive\n\n")
        events = bus.get_run_events()
        self.assertEqual(events[-1]["type"], "keepalive")

        bus.cancel()
        self.assertTrue(bus.is_cancelled())
        self.assertIsNone(next(comments, None))


if __name__ == "__main__":
    unittest.main()
