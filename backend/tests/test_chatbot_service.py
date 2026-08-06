import unittest
from unittest.mock import patch

from rag.src.chatbot import ChatbotService
from rag.src.preprocess import QueryPreprocessor


class FakeNoticeRepository:
    source_name = "fake"

    def __init__(self):
        self.notices = {
            10: {
                "id": 10,
                "source_notice_id": "100010",
                "title": "장학금 신청 안내",
                "url": "https://example.test/10",
                "category": ["장학/근로"],
                "content": "신청 마감은 8월 20일입니다.",
                "published_at": "2026-08-01",
                "deadline": "2026-08-20T23:59:00+09:00",
            }
        }

    def fetch_notices(self):
        return list(self.notices.values())

    def fetch_notice(self, notice_id):
        return self.notices.get(int(notice_id))


class ChatbotServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = ChatbotService(
            model=object(),
            preprocessor=QueryPreprocessor(),
            search_source="notices",
            notice_repository=FakeNoticeRepository(),
            notices=[],
            notice_embeddings=None,
        )

    def test_restores_candidate_ids_and_answers_number_selection(self):
        state = {
            "last_search_query": "장학 공지 알려줘",
            "referenced_notice_ids": [10],
            "shown_notice_ids": [10],
            "candidate_notice_ids": [10],
            "active_notice_id": None,
            "pending_answer_question": "장학 공지 알려줘",
        }

        with patch(
            "rag.src.chatbot.generate_answer",
            return_value="8월 20일까지 신청할 수 있습니다.",
        ):
            result = self.service.handle_message("1번", state)

        self.assertEqual(result.answer, "8월 20일까지 신청할 수 있습니다.")
        self.assertEqual(result.state["active_notice_id"], 10)
        self.assertEqual(result.sources[0]["id"], 10)

    def test_reset_discards_client_state(self):
        result = self.service.handle_message(
            "초기화",
            {"last_search_query": "이전 질문", "shown_notice_ids": [10]},
        )

        self.assertIsNone(result.state["last_search_query"])
        self.assertEqual(result.state["shown_notice_ids"], [])


if __name__ == "__main__":
    unittest.main()
