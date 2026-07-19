import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from rag.src.llm import generate_answer


class FakeResponse:
    text = "알고리즘 시험은 6월 18일입니다."


class FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return FakeResponse()


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


class AnswerPromptTests(unittest.TestCase):
    def test_exam_question_keeps_original_question_and_requires_row_lookup(self):
        client = FakeClient()
        results = [{
            "notice": {
                "id": 1,
                "title": "기말고사 일정",
                "category": "학사",
                "published_at": "2026-06-01",
                "content": "알고리즘 | 6월 18일 | 10:00 | Z2-101",
                "url": "https://example.com/1",
            },
        }]

        generate_answer(
            question="알고리즘 시험 언제야?",
            relevant_results=results,
            now=datetime(2026, 6, 10, 12, 0, tzinfo=ZoneInfo("Asia/Seoul")),
            client=client,
        )

        prompt = client.models.calls[0]["contents"]
        self.assertIn("알고리즘 시험 언제야?", prompt)
        self.assertIn("정확히 일치하는 과목 행", prompt)
        self.assertIn("2026-06-10T12:00:00+09:00", prompt)


if __name__ == "__main__":
    unittest.main()
