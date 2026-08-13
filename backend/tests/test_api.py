import unittest

from fastapi.testclient import TestClient

from backend.app.dependencies import get_chatbot_service, get_push_service
from backend.app.main import create_app
from backend.app.push_service import PushSubscriptionService
from rag.src.chatbot import ChatResult

from backend.tests.test_push_service import FakePushRepository


class FakeChatbotService:
    def handle_message(
        self,
        message,
        state_snapshot=None,
        selected_notice_id=None,
        load_more=False,
        candidate_page=None,
    ):
        answer = (
            f"선택: {selected_notice_id}"
            if selected_notice_id is not None
            else "추가 공지"
            if load_more
            else f"답변: {message}"
        )
        return ChatResult(
            answer=answer,
            state={
                "last_search_query": message,
                "referenced_notice_ids": [],
                "shown_notice_ids": [],
                "candidate_notice_ids": [],
                "active_notice_id": None,
                "pending_answer_question": None,
            },
            sources=[],
        )


class BackendApiTests(unittest.TestCase):
    def setUp(self):
        self.repository = FakePushRepository()
        self.push_service = PushSubscriptionService(self.repository)
        self.app = create_app()
        self.app.dependency_overrides[get_push_service] = (
            lambda: self.push_service
        )
        self.app.dependency_overrides[get_chatbot_service] = (
            lambda: FakeChatbotService()
        )
        self.client = TestClient(self.app)

    def test_health(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_registers_push_subscription_with_frontend_contract(self):
        response = self.client.post(
            "/api/push/subscriptions",
            json={
                "subscription": {
                    "endpoint": "https://push.example.test/subscription/1",
                    "keys": {"p256dh": "key", "auth": "auth"},
                },
                "categories": ["academic", "scholarship"],
            },
        )

        self.assertEqual(response.status_code, 201)
        payload = response.json()
        self.assertTrue(payload["created"])
        self.assertTrue(payload["managementToken"])
        row = self.repository.rows[payload["subscriptionId"]]
        self.assertEqual(row["categories"], ["학사", "장학/근로"])

    def test_updates_categories_with_management_token(self):
        registered = self.client.post(
            "/api/push/subscriptions",
            json={
                "subscription": {
                    "endpoint": "https://push.example.test/subscription/1",
                    "keys": {"p256dh": "key", "auth": "auth"},
                },
                "categories": ["academic"],
            },
        ).json()

        response = self.client.patch(
            f"/api/push/subscriptions/{registered['subscriptionId']}",
            headers={
                "X-Subscription-Token": registered["managementToken"],
            },
            json={"categories": ["career"]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["categories"], ["취업/인턴"])

    def test_chat_contract(self):
        response = self.client.post(
            "/api/chat",
            json={"message": "장학 공지 알려줘", "state": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "답변: 장학 공지 알려줘")
        self.assertFalse(response.json()["hasMore"])
        self.assertEqual(
            response.json()["state"]["last_search_query"],
            "장학 공지 알려줘",
        )

    def test_selects_notice_with_explicit_action(self):
        response = self.client.post(
            "/api/chat",
            json={
                "action": "select_notice",
                "selected_notice_id": 10,
                "state": None,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "선택: 10")

    def test_loads_more_notices_with_explicit_action(self):
        response = self.client.post(
            "/api/chat",
            json={
                "action": "load_more",
                "state": {"last_search_query": "장학금 공지"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "추가 공지")


if __name__ == "__main__":
    unittest.main()
