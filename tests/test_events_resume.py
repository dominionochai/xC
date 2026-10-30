"""Resume semantics exercised against the bounded EventBus buffer."""

import unittest

from agents.events import EventBus


RUN_NOT_RESUMABLE = "RUN_NOT_RESUMABLE"


def replay_after(bus, last_event_id):
    """Replay retained events, or flag a cursor whose next event was evicted.

    EventBus has no replay API; this test-local helper reads get_run_events()
    to exercise its ring-buffer semantics and model the resume status expected
    when the requested cursor predates the retained buffer.
    """
    retained = bus.get_run_events()
    if retained and last_event_id < retained[0]["seq"] - 1:
        return RUN_NOT_RESUMABLE
    return [event for event in retained if event["seq"] > last_event_id]


class EventResumeTests(unittest.TestCase):
    def test_reset_starts_a_new_run_sequence_at_one(self):
        bus = EventBus()
        bus.emit("started", {"run": "old"})
        bus.emit("progress", {"run": "old"})

        bus.reset()
        first = bus.emit("started", {"run": "new"})
        second = bus.emit("progress", {"run": "new"})

        self.assertEqual(first["seq"], 1)
        self.assertEqual(second["seq"], 2)
        self.assertEqual(
            [event["seq"] for event in bus.get_run_events()], [1, 2]
        )

    def test_replay_returns_events_after_last_event_id_in_order(self):
        bus = EventBus()
        for name in ("started", "progress", "progress", "completed"):
            bus.emit(name, {"name": name})

        replayed = replay_after(bus, last_event_id=2)

        self.assertEqual([event["seq"] for event in replayed], [3, 4])
        self.assertEqual(
            [event["type"] for event in replayed], ["progress", "completed"]
        )

    def test_evicted_cursor_is_not_resumable(self):
        bus = EventBus()
        for index in range(5002):
            bus.emit("tick", {"index": index})

        retained = bus.get_run_events()
        retained_ids = [event["seq"] for event in retained]

        self.assertEqual(len(retained), 5000)
        self.assertNotIn(1, retained_ids)
        self.assertEqual(retained[0]["seq"], 3)
        self.assertEqual(replay_after(bus, last_event_id=1), RUN_NOT_RESUMABLE)


if __name__ == "__main__":
    unittest.main()
