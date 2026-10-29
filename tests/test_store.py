import os
import tempfile
import unittest
from unittest.mock import patch

from store.store import MemoryStore, SqliteStore


class MemoryStoreTests(unittest.TestCase):
    def test_crud_round_trip(self):
        store = MemoryStore()
        store.create("key", "first")
        self.assertEqual(store.get("key"), "first")

        store.update("key", "second")
        self.assertEqual(store.get("key"), "second")
        self.assertEqual(len(store.list()), 1)


class SqliteStoreTests(unittest.TestCase):
    def test_persists_across_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            db_path = os.path.join(directory, "store.sqlite")
            with patch.dict(os.environ, {"XC_DB_PATH": db_path}):
                first = SqliteStore()
                first.create("key", "value")
                first.close()
                del first

                second = SqliteStore()
                self.assertEqual(second.get("key"), "value")
                self.assertEqual(len(second.list()), 1)
                second.close()

    def test_default_in_memory_store(self):
        with patch.dict(os.environ):
            os.environ.pop("XC_DB_PATH", None)
            store = SqliteStore()
            store.create("key", "value")
            self.assertEqual(store.get("key"), "value")
            store.close()


if __name__ == "__main__":
    unittest.main()
