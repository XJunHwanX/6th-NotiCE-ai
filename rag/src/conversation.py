from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

if __package__:
    from .intent import QueryIntent
    from .preprocess import ProcessedQuery
else:
    from intent import QueryIntent
    from preprocess import ProcessedQuery


@dataclass(frozen=True)
class QueryResolution:
    raw_question: str
    normalized_question: str
    search_question: str
    intent: QueryIntent
    exclude_notice_ids: tuple[Any, ...] = ()
    clarification: str | None = None


@dataclass
class ConversationState:
    """DB 연결 전에도 사용할 수 있는 한 세션의 검색 상태입니다."""

    last_search_query: str | None = None
    referenced_notice_ids: list[Any] = field(default_factory=list)
    shown_notice_ids: list[Any] = field(default_factory=list)
    candidate_results: list[dict] = field(default_factory=list)
    active_result: dict | None = None
    pending_answer_question: str | None = None
    router_context: list[dict[str, str]] = field(default_factory=list)
    candidate_page: int = 1

    @property
    def has_context(self) -> bool:
        return self.last_search_query is not None

    @property
    def has_candidates(self) -> bool:
        return bool(self.candidate_results)

    def select_candidate(
        self,
        question: str,
    ) -> tuple[dict | None, str | None]:
        if not self.candidate_results:
            return None, None

        selectable_results = self._selectable_results()

        normalized = " ".join(question.strip().split())
        compact = normalized.replace(" ", "")
        selection_number = None
        number_match = re.match(r"^(\d+)번", compact)

        if number_match:
            selection_number = int(number_match.group(1))
        else:
            ordinal_numbers = {
                "첫번째": 1,
                "두번째": 2,
                "세번째": 3,
                "네번째": 4,
                "다섯번째": 5,
            }

            for ordinal, number in ordinal_numbers.items():
                if compact.startswith(ordinal):
                    selection_number = number
                    break

        if selection_number is None:
            title_matches = []

            for result in selectable_results:
                title = str(result.get("notice", {}).get("title") or "")

                if title and title in normalized:
                    title_matches.append(result)

            if len(title_matches) == 1:
                selected = title_matches[0]
            else:
                return None, None
        elif selection_number < 1 or selection_number > len(selectable_results):
            return None, (
                f"1번부터 {len(selectable_results)}번 사이에서 선택해주세요."
            )
        else:
            selected = selectable_results[selection_number - 1]

        self.active_result = selected
        notice_id = selected.get("notice", {}).get("id")
        self.referenced_notice_ids = [notice_id] if notice_id is not None else []
        return selected, None

    def select_candidate_by_id(self, notice_id: Any) -> dict | None:
        """현재 검색 후보에 포함된 공지만 명시적인 ID로 선택합니다."""
        selected = next(
            (
                result
                for result in self._selectable_results()
                if str(result.get("notice", {}).get("id")) == str(notice_id)
            ),
            None,
        )
        if selected is None:
            return None

        self.active_result = selected
        selected_id = selected.get("notice", {}).get("id")
        self.referenced_notice_ids = (
            [selected_id] if selected_id is not None else []
        )
        return selected

    def _selectable_results(self) -> list[dict]:
        """페이지에서 사용자에게 실제 공개된 후보만 선택 대상으로 반환합니다."""
        if not self.shown_notice_ids:
            return self.candidate_results

        shown_ids = {str(notice_id) for notice_id in self.shown_notice_ids}
        return [
            result
            for result in self.candidate_results
            if str(result.get("notice", {}).get("id")) in shown_ids
        ]

    def resolve(
        self,
        query: ProcessedQuery,
        intent: QueryIntent,
    ) -> QueryResolution:
        if intent == QueryIntent.MORE_RESULTS:
            if not self.last_search_query:
                return QueryResolution(
                    raw_question=query.raw,
                    normalized_question=query.normalized,
                    search_question=query.normalized,
                    intent=intent,
                    clarification=(
                        "어떤 종류의 공지를 더 찾을까요? "
                        "장학금, 인턴, 졸업처럼 주제를 알려주세요."
                    ),
                )

            return QueryResolution(
                raw_question=query.raw,
                normalized_question=query.normalized,
                search_question=self.last_search_query,
                intent=intent,
                exclude_notice_ids=tuple(self.shown_notice_ids),
            )

        if intent == QueryIntent.FOLLOW_UP and self.last_search_query:
            return QueryResolution(
                raw_question=query.raw,
                normalized_question=query.normalized,
                search_question=(
                    f"{self.last_search_query}. "
                    f"후속 질문: {query.normalized}"
                ),
                intent=intent,
            )

        return QueryResolution(
            raw_question=query.raw,
            normalized_question=query.normalized,
            search_question=query.normalized,
            intent=intent,
        )

    def record_results(
        self,
        resolution: QueryResolution,
        results: list[dict],
        answer_question: str | None = None,
    ) -> None:
        notice_ids = []

        for result in results:
            notice_id = result.get("notice", {}).get("id")
            if notice_id is not None and notice_id not in notice_ids:
                notice_ids.append(notice_id)

        self.active_result = None
        self.pending_answer_question = (
            answer_question or resolution.search_question
        )

        self.referenced_notice_ids = notice_ids
        self.candidate_results = list(results)
        self.last_search_query = resolution.search_question
        self.shown_notice_ids = notice_ids.copy()
        self.candidate_page = 1

    def snapshot(self) -> dict:
        """나중에 chat_sessions에 그대로 저장할 수 있는 상태를 반환합니다."""
        return {
            "last_search_query": self.last_search_query,
            "referenced_notice_ids": self.referenced_notice_ids.copy(),
            "shown_notice_ids": self.shown_notice_ids.copy(),
            "candidate_notice_ids": [
                result.get("notice", {}).get("id")
                for result in self.candidate_results
                if result.get("notice", {}).get("id") is not None
            ],
            "active_notice_id": (
                self.active_result.get("notice", {}).get("id")
                if self.active_result
                else None
            ),
            "pending_answer_question": self.pending_answer_question,
            "candidate_page": self.candidate_page,
            "router_context": [
                {"role": message["role"], "content": message["content"]}
                for message in self.router_context
            ],
        }
        
    def add_message(self, role: str, content: str) -> None:
        self.router_context.append(
        {
            "role": role,
            "content": content.strip(),
        }
    )
        # 최근 6개 메시지만 유지 (최근 3턴)
        if len(self.router_context) > 6:
            self.router_context = self.router_context[-6:]    
    
    def build_router_context(self) -> str:
        recent_history = "\n".join(
        f"{message['role']}: {message['content']}"
        for message in self.router_context
        )
        
        active_notice_id = None
        active_notice_title = None
        
        if self.active_result:
            notice = self.active_result.get("notice", {})
            active_notice_id = notice.get("id")
            active_notice_title = notice.get("title")
            
        return (
            f"[최근 대화]\n"
            f"{recent_history or '없음'}\n\n"
            f"[이전 검색 질문]\n"
            f"{self.last_search_query or '없음'}\n\n"
            f"[선택된 공지]\n"
            f"- ID: {active_notice_id if active_notice_id is not None else '없음'}\n"
            f"- 제목: {active_notice_title or '없음'}"
        )   
