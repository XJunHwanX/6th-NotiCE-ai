from __future__ import annotations

import re
from enum import Enum


class QueryIntent(str, Enum):
    GENERAL_SEARCH = "general_search"
    FOLLOW_UP = "follow_up"
    MORE_RESULTS = "more_results"
    DEADLINE_RELAXED = "deadline_relaxed"
    DEADLINE_URGENT = "deadline_urgent"
    EXAM_LOCATION = "exam_location"
    NOTICE_SUMMARY = "notice_summary"


MORE_RESULT_PATTERNS = (
    "다른 건",
    "다른건",
    "더 없어",
    "더없어",
    "추가로",
    "또 없어",
)

RELAXED_DEADLINE_PATTERNS = (
    "널널",
    "여유",
    "많이 남",
    "오래 남",
)

URGENT_DEADLINE_PATTERNS = (
    "곧 마감",
    "마감 임박",
    "급한",
    "얼마 안 남",
    "마감 가까",
    "신청 가능",
    "모집 중",
    "접수 중",
    "마감 안 지난",
)

FOLLOW_UP_TOPICS = {
    "서류",
    "마감",
    "기간",
    "대상",
    "장소",
    "방법",
    "신청",
    "지원",
    "자격",
    "문의",
    "일정",
    "혜택",
    "상금",
    "주최",
    "내용",
}


def classify_intent(question: str, has_context: bool = False) -> QueryIntent:
    """규칙 기반으로 검색 경로를 선택할 수 있는 질문 의도를 분류합니다."""
    normalized = " ".join(question.lower().split())

    if any(pattern in normalized for pattern in MORE_RESULT_PATTERNS):
        return QueryIntent.MORE_RESULTS

    if "요약" in normalized:
        return QueryIntent.NOTICE_SUMMARY

    has_exam_word = any(
        word in normalized
        for word in ("시험", "중간", "기말")
    )
    has_location_word = any(
        word in normalized
        for word in ("장소", "강의실", "교실", "어디")
    )

    if has_exam_word and has_location_word:
        return QueryIntent.EXAM_LOCATION

    if any(pattern in normalized for pattern in RELAXED_DEADLINE_PATTERNS):
        return QueryIntent.DEADLINE_RELAXED

    if any(pattern in normalized for pattern in URGENT_DEADLINE_PATTERNS):
        return QueryIntent.DEADLINE_URGENT

    tokens = re.findall(r"[0-9a-zA-Z가-힣]+", normalized)
    has_follow_up_topic = any(
        topic in normalized
        for topic in FOLLOW_UP_TOPICS
    )

    if has_context and len(tokens) <= 4 and has_follow_up_topic:
        return QueryIntent.FOLLOW_UP

    return QueryIntent.GENERAL_SEARCH
