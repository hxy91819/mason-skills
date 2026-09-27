import unittest
from src.api import list_users
from src.other_api import get_user
from src.store import Store


class UserContract(unittest.TestCase):
    def setUp(self):
        self.store = Store([(1, "A", "Alice"), (2, "A", "Bob"), (3, "B", "Carol")])
        self.addCleanup(self.store.close)

    def test_tenant_filter(self):
        self.assertEqual(list_users(self.store, "A", [3]), [])
        self.assertEqual(list_users(self.store, "B", [1, 2, 3]), [{"id": 3, "name": "Carol"}])

    def test_order_and_duplicates(self):
        self.assertEqual(list_users(self.store, "A", [2, 1, 2]), [
            {"id": 2, "name": "Bob"}, {"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

    def test_missing_rows(self):
        self.assertEqual(list_users(self.store, "A", [99, 1]), [{"id": 1, "name": "Alice"}])

    def test_empty(self):
        self.assertEqual(list_users(self.store, "A", []), [])
        self.assertEqual(self.store.selects, 0)

    def test_other_entry_keeps_behavior(self):
        self.assertEqual(get_user(self.store, "A", 1), {"id": 1, "name": "Alice"})
        self.assertIsNone(get_user(self.store, "A", 3))
        self.assertIsNone(get_user(self.store, "A", 99))

    def test_returned_objects_do_not_alias(self):
        result = list_users(self.store, "A", [1, 1])
        result[0]["name"] = "modified"
        self.assertEqual(result[1]["name"], "Alice")
        self.assertEqual(get_user(self.store, "A", 1)["name"], "Alice")

    def test_multiple_batch_boundaries(self):
        self.assertEqual(list_users(self.store, "A", [1] * 205), [{"id": 1, "name": "Alice"}] * 205)

    def test_database_failure_is_not_silenced(self):
        class FailingStore:
            def one(self, _):
                raise RuntimeError("unavailable")
            def many(self, _):
                raise RuntimeError("unavailable")
        with self.assertRaisesRegex(RuntimeError, "unavailable"):
            list_users(FailingStore(), "A", [1])
