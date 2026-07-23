import unittest
from datetime import datetime, timezone

from rag.src.intent import QueryIntent
from rag.src.router import (
    QueryRoute,
    create_fallback_plan,
    create_router_prompt,
    plan_question,
    route_to_intent,
)


class FakeResponse:
    def __init__(self, parsed=None, text=None):
        self.parsed = parsed
        self.text = text


class FakeModels:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)

        if self.error:
            raise self.error

        return self.response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response=response, error=error)


class QueryRouterTests(unittest.TestCase):
    def test_uses_structured_llm_plan(self):
        client = FakeClient(FakeResponse(parsed={
            "route": "exam_notice_search",
            "search_query": "배OO 교수 알고리즘 기말고사 장소",
            "confidence": 0.94,
            "clarification": None,
        }))

        plan = plan_question(
            question="배OO 교수가 담당하는 알고리즘 과목 기말 어디서 봐?",
            client=client,
        )

        self.assertEqual(plan.route, QueryRoute.EXAM_NOTICE_SEARCH)
        self.assertEqual(
            plan.search_query,
            "배OO 교수 알고리즘 기말고사 장소",
        )
        self.assertEqual(plan.source, "llm")
        config = client.models.calls[0]["config"]
        self.assertEqual(config.response_mime_type, "application/json")
        self.assertEqual(config.temperature, 0)

    def test_router_prompt_includes_time_and_conversation_state(self):
        prompt = create_router_prompt(
            question="내일 마감하는 공지 있어?",
            has_context=True,
            has_active_notice=False,
            now=datetime(2026, 7, 19, 6, 30, tzinfo=timezone.utc),
        )

        self.assertIn("2026-07-19T15:30:00+09:00", prompt)
        self.assertIn("이전 검색 맥락 존재: True", prompt)
        self.assertIn("선택된 공지 존재: False", prompt)

    def test_falls_back_to_rules_when_llm_call_fails(self):
        client = FakeClient(error=RuntimeError("temporary failure"))

        plan = plan_question(
            question="기말 시험 어디서 봐?",
            client=client,
        )

        self.assertEqual(plan.route, QueryRoute.EXAM_NOTICE_SEARCH)
        self.assertEqual(plan.source, "fallback")

    def test_falls_back_when_llm_returns_blank_search_query(self):
        client = FakeClient(FakeResponse(parsed={
            "route": "notice_search",
            "search_query": "   ",
            "confidence": 0.8,
            "clarification": None,
        }))

        plan = plan_question(question="장학금 공지", client=client)

        self.assertEqual(plan.route, QueryRoute.NOTICE_SEARCH)
        self.assertEqual(plan.search_query, "장학금 공지")
        self.assertEqual(plan.source, "fallback")

    def test_exam_time_rule_overrides_wrong_llm_route(self):
        question = "자료구조및프로그래밍 자료구조 이혜영 시험언제냐"
        client = FakeClient(FakeResponse(parsed={
            "route": "notice_search",
            "search_query": "자료구조 공지",
            "confidence": 0.8,
            "clarification": None,
        }))

        plan = plan_question(question=question, client=client)

        self.assertEqual(plan.route, QueryRoute.EXAM_NOTICE_SEARCH)
        self.assertEqual(plan.search_query, question)
        self.assertEqual(plan.source, "rule")

    def test_fallback_detects_open_notice_search(self):
        plan = create_fallback_plan("곧 마감인 공지 있어?")

        self.assertEqual(plan.route, QueryRoute.OPEN_NOTICE_SEARCH)

    def test_adds_default_clarification_when_llm_omits_it(self):
        client = FakeClient(FakeResponse(parsed={
            "route": "clarification",
            "search_query": "공지",
            "confidence": 0.7,
            "clarification": None,
        }))

        plan = plan_question(question="그거", client=client)

        self.assertEqual(plan.route, QueryRoute.CLARIFICATION)
        self.assertIsNotNone(plan.clarification)

    def test_maps_search_routes_to_existing_conversation_intents(self):
        self.assertEqual(
            route_to_intent(QueryRoute.NOTICE_SEARCH),
            QueryIntent.GENERAL_SEARCH,
        )
        self.assertEqual(
            route_to_intent(QueryRoute.OPEN_NOTICE_SEARCH),
            QueryIntent.DEADLINE_URGENT,
        )
        self.assertEqual(
            route_to_intent(QueryRoute.EXAM_NOTICE_SEARCH),
            QueryIntent.EXAM_LOCATION,
        )


if __name__ == "__main__":
    unittest.main()
