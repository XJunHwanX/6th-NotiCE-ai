import unittest

from backend.app.push_service import (
    InvalidManagementTokenError,
    PushSubscriptionService,
    hash_management_token,
    normalize_categories,
)


class FakePushRepository:
    def __init__(self):
        self.rows = {}
        self.next_id = 1

    def find_by_endpoint(self, endpoint):
        return next(
            (row for row in self.rows.values() if row["endpoint"] == endpoint),
            None,
        )

    def fetch_by_id(self, subscription_id):
        return self.rows.get(subscription_id)

    def insert(self, values):
        subscription_id = str(self.next_id)
        self.next_id += 1
        row = {"id": subscription_id, **values}
        self.rows[subscription_id] = row
        return row

    def update(self, subscription_id, values):
        self.rows[subscription_id].update(values)
        return self.rows[subscription_id]

    def delete(self, subscription_id):
        self.rows.pop(subscription_id)


class PushSubscriptionServiceTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakePushRepository()
        self.service = PushSubscriptionService(self.repository)

    def test_maps_frontend_category_ids_to_pipeline_categories(self):
        self.assertEqual(
            normalize_categories(["academic", "scholarship", "academic"]),
            ["학사", "장학/근로"],
        )

    def test_registers_and_updates_same_endpoint(self):
        first = self.service.register(
            endpoint="https://push.example.test/subscription/1",
            p256dh="key-1",
            auth="auth-1",
            category_ids=["academic"],
        )
        second = self.service.register(
            endpoint="https://push.example.test/subscription/1",
            p256dh="key-2",
            auth="auth-2",
            category_ids=["career"],
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(first.subscription_id, second.subscription_id)
        self.assertEqual(len(self.repository.rows), 1)
        row = self.repository.rows[first.subscription_id]
        self.assertEqual(row["categories"], ["취업/인턴"])
        self.assertEqual(row["p256dh"], "key-2")

    def test_empty_categories_disable_delivery(self):
        result = self.service.register(
            endpoint="https://push.example.test/subscription/1",
            p256dh="key",
            auth="auth",
            category_ids=[],
        )

        self.assertFalse(self.repository.rows[result.subscription_id]["enabled"])

    def test_management_token_is_required_to_change_preferences(self):
        result = self.service.register(
            endpoint="https://push.example.test/subscription/1",
            p256dh="key",
            auth="auth",
            category_ids=["academic"],
        )

        with self.assertRaises(InvalidManagementTokenError):
            self.service.update_preferences(
                subscription_id=result.subscription_id,
                management_token="wrong-token",
                category_ids=["career"],
                enabled=None,
            )

        row = self.service.update_preferences(
            subscription_id=result.subscription_id,
            management_token=result.management_token,
            category_ids=["career"],
            enabled=None,
        )
        self.assertEqual(row["categories"], ["취업/인턴"])
        self.assertEqual(
            row["management_token_hash"],
            hash_management_token(result.management_token),
        )


if __name__ == "__main__":
    unittest.main()
