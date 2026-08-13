import unittest
from unittest.mock import patch

from rag.src.chatbot import ChatbotService
from rag.src.llm import NoticeCandidateDecision
from rag.src.preprocess import QueryPreprocessor
from rag.src.router import QueryPlan, QueryRoute


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
        for notice_id in range(2, 6):
            self.notices[notice_id] = {
                "id": notice_id,
                "source_notice_id": f"10000{notice_id}",
                "title": f"장학 공지 {notice_id}",
                "url": f"https://example.test/{notice_id}",
                "category": ["장학/근로"],
                "content": f"장학 공지 {notice_id} 내용",
                "published_at": f"2026-08-{20 - notice_id:02d}",
                "deadline": None,
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

    def test_answers_explicit_notice_id_selection(self):
        state = {
            "last_search_query": "장학 공지 알려줘",
            "candidate_notice_ids": [10],
            "pending_answer_question": "장학 공지 알려줘",
        }

        with patch(
            "rag.src.chatbot.generate_answer",
            return_value="8월 20일까지 신청할 수 있습니다.",
        ):
            result = self.service.handle_message(
                "",
                state,
                selected_notice_id=10,
            )

        self.assertEqual(result.answer, "8월 20일까지 신청할 수 있습니다.")
        self.assertEqual(result.state["active_notice_id"], 10)
        self.assertFalse(result.selection_required)

    def test_rejects_notice_id_outside_current_candidates(self):
        result = self.service.handle_message(
            "",
            {"candidate_notice_ids": [10]},
            selected_notice_id=999,
        )

        self.assertIn("현재 검색 결과에 없는 공지", result.answer)
        self.assertIsNone(result.state["active_notice_id"])

    def test_rejects_hidden_candidate_until_its_page_is_visible(self):
        state = {
            "shown_notice_ids": [10, 2, 3],
            "candidate_notice_ids": [10, 2, 3, 4, 5],
        }

        result = self.service.handle_message(
            "",
            state,
            selected_notice_id=4,
        )

        self.assertIn("현재 검색 결과에 없는 공지", result.answer)
        self.assertIsNone(result.state["active_notice_id"])

    def test_candidate_page_uses_only_requested_three_without_search(self):
        state = {
            "last_search_query": "장학금 공지",
            "shown_notice_ids": [10, 2, 3],
            "candidate_notice_ids": [10, 2, 3, 4, 5],
        }

        with patch.object(self.service, "_search") as search:
            result = self.service.handle_message("", state, candidate_page=2)

        search.assert_not_called()
        self.assertEqual(
            [source["id"] for source in result.sources],
            [4, 5],
        )
        self.assertEqual(result.state["shown_notice_ids"], [4, 5])
        self.assertEqual(result.state["candidate_page"], 2)
        self.assertTrue(result.selection_required)
        self.assertFalse(result.has_more)
        self.assertEqual(result.page, 2)
        self.assertEqual(result.page_count, 2)

    def test_candidate_page_clamps_to_last_page(self):
        state = {
            "last_search_query": "장학금 공지",
            "shown_notice_ids": [10, 2, 3, 4, 5],
            "candidate_notice_ids": [10, 2, 3, 4, 5],
        }

        with patch.object(self.service, "_search") as search:
            result = self.service.handle_message("", state, candidate_page=99)

        search.assert_not_called()
        self.assertEqual(
            [source["id"] for source in result.sources],
            [4, 5],
        )
        self.assertTrue(result.selection_required)
        self.assertFalse(result.has_more)

    def test_general_message_uses_llm_router_with_conversation_context(self):
        state = {
            "last_search_query": "프로그래밍언어론 서버 IP",
            "router_context": [
                {"role": "user", "content": "프언론 서버 IP 알려줘"},
                {"role": "assistant", "content": "관련 공지를 안내했습니다."},
            ],
        }
        plan = QueryPlan(
            route=QueryRoute.GENERAL_CHAT,
            search_query="안녕하세요",
            confidence=0.99,
        )

        with (
            patch("rag.src.chatbot.plan_question", return_value=plan) as router,
            patch(
                "rag.src.chatbot.generate_general_answer",
                return_value="안녕하세요!",
            ),
        ):
            result = self.service.handle_message("안녕", state)

        router.assert_called_once()
        router_context = router.call_args.kwargs["router_context"]
        self.assertIn("프언론 서버 IP 알려줘", router_context)
        self.assertIn("프로그래밍언어론 서버 IP", router_context)
        self.assertEqual(result.answer, "안녕하세요!")
        self.assertEqual(result.state["router_context"][-2]["content"], "안녕")
        self.assertEqual(result.state["router_context"][-1]["content"], "안녕하세요!")

    def test_list_decision_caches_selected_candidates_newest_first(self):
        search_results = [
            {"notice": self.service.notice_repository.fetch_notice(notice_id)}
            for notice_id in [5, 4, 3, 2]
        ]
        plan = QueryPlan(
            route=QueryRoute.NOTICE_SEARCH,
            search_query="장학금 공지",
            confidence=0.95,
        )

        with (
            patch("rag.src.chatbot.plan_question", return_value=plan),
            patch.object(self.service, "_search", return_value=search_results),
            patch(
                "rag.src.chatbot.judge_notice_candidates",
                return_value=NoticeCandidateDecision(
                    mode="list",
                    notice_ids=[5, 4, 3, 2],
                ),
            ),
        ):
            result = self.service.handle_message("장학금 알려줘")

        self.assertEqual(result.state["candidate_notice_ids"], [2, 3, 4, 5])
        self.assertEqual(result.state["shown_notice_ids"], [2, 3, 4])
        self.assertEqual([source["id"] for source in result.sources], [2, 3, 4])
        self.assertTrue(result.has_more)

    def test_logs_router_interpretation_and_searched_notices(self):
        search_results = [
            {
                "notice": self.service.notice_repository.fetch_notice(10),
                "hybrid_score": 0.91,
                "semantic_score": 0.9,
                "keyword_score": 0.8,
                "matched_keywords": ["장학금"],
            }
        ]
        plan = QueryPlan(
            route=QueryRoute.NOTICE_SEARCH,
            search_query="장학금 공지",
            confidence=0.93,
        )

        with (
            patch("rag.src.chatbot.plan_question", return_value=plan),
            patch.object(self.service, "_search", return_value=search_results),
            patch(
                "rag.src.chatbot.judge_notice_candidates",
                return_value=NoticeCandidateDecision(
                    mode="answer",
                    notice_ids=[10],
                    reason="장학금 신청 기한을 답할 수 있음",
                ),
            ),
            patch(
                "rag.src.chatbot.generate_answer",
                return_value="장학금 안내입니다.",
            ),
            self.assertLogs("uvicorn.error", level="INFO") as logs,
        ):
            self.service.handle_message("장학금 알려줘")

        output = "\n".join(logs.output)
        self.assertIn("[chat.router]", output)
        self.assertIn("search_query='장학금 공지'", output)
        self.assertIn("[chat.search]", output)
        self.assertIn("장학금 신청 안내", output)
        self.assertIn("hybrid=0.9100", output)
        self.assertIn("filter_status=pending", output)
        self.assertIn("[chat.judge] mode=answer searched=1 selected=1", output)

    def test_not_found_decision_does_not_expose_search_candidates(self):
        search_results = [
            {"notice": self.service.notice_repository.fetch_notice(10)}
        ]
        plan = QueryPlan(
            route=QueryRoute.NOTICE_SEARCH,
            search_query="없는 공지",
            confidence=0.9,
        )
        with (
            patch("rag.src.chatbot.plan_question", return_value=plan),
            patch.object(self.service, "_search", return_value=search_results),
            patch(
                "rag.src.chatbot.judge_notice_candidates",
                return_value=NoticeCandidateDecision(mode="not_found"),
            ),
        ):
            result = self.service.handle_message("없는 공지 알려줘")

        self.assertIn("관련 내용을 찾지 못했습니다", result.answer)
        self.assertEqual(result.sources, [])
        self.assertFalse(result.selection_required)

    def test_reset_discards_client_state(self):
        result = self.service.handle_message(
            "초기화",
            {"last_search_query": "이전 질문", "shown_notice_ids": [10]},
        )

        self.assertIsNone(result.state["last_search_query"])
        self.assertEqual(result.state["shown_notice_ids"], [])


if __name__ == "__main__":
    unittest.main()
