"""Schema and lazy-loading tests for report persistence."""

import builtins
import importlib
import importlib.util
import unittest
from unittest.mock import patch

from backend.src import db


class LazyDependencyTests(unittest.TestCase):
    def test_import_does_not_require_sqlalchemy(self) -> None:
        original_import = builtins.__import__

        def without_sqlalchemy(name, *args, **kwargs):
            if name == "sqlalchemy" or name.startswith("sqlalchemy."):
                raise ModuleNotFoundError("simulated missing SQLAlchemy")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=without_sqlalchemy):
            module = importlib.reload(db)
            with self.assertRaisesRegex(RuntimeError, "SQLAlchemy"):
                module.get_engine()
        # Restore a clean module state for the model inspection tests.
        importlib.reload(db)


@unittest.skipUnless(importlib.util.find_spec("sqlalchemy"), "SQLAlchemy is not installed")
class ReportSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        from sqlalchemy.dialects import postgresql
        from sqlalchemy.schema import CreateTable

        cls.postgresql = postgresql
        cls.CreateTable = CreateTable
        cls.model = db.ReportRecord

    def test_report_model_columns_and_json_types(self) -> None:
        table = self.model.__table__
        self.assertEqual(table.name, "reports")
        self.assertEqual(set(table.primary_key.columns.keys()), {"id"})
        self.assertEqual(table.c.status.type.length, 32)
        self.assertEqual(table.c["input"].type.__class__.__name__, "JSON")
        self.assertEqual(table.c.result.type.__class__.__name__, "JSON")
        self.assertTrue(table.c.created_at.type.timezone)
        self.assertTrue(table.c.updated_at.type.timezone)

    def test_schema_compiles_for_postgresql_without_a_live_database(self) -> None:
        sql = str(self.CreateTable(self.model.__table__).compile(dialect=self.postgresql.dialect()))
        self.assertIn("CREATE TABLE reports", sql)
        self.assertIn("input JSON NOT NULL", sql)
        self.assertIn("result JSON", sql)
        self.assertIn("TIMESTAMP WITH TIME ZONE", sql)
