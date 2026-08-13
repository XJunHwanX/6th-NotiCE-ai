from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

import numpy as np

from .config import EMBEDDING_MODEL_NAME
from .conversation import ConversationState
from .db import (
    AliasRepositoryError,
    ChunkRepository,
    ChunkRepositoryError,
    NoticeRepository,
    NoticeRepositoryError,
    get_alias_repository,
    get_chunk_repository,
    get_notice_repository,
    get_rag_search_source,
)
from .llm import generate_answer, generate_general_answer
from .preprocess import DEFAULT_PREPROCESSOR, QueryPreprocessor
from .retriever import (
    search_notice_chunks,
    search_notice_chunks_keyword_only,
)
from .router import QueryRoute, get_current_datetime, plan_question, route_to_intent
from .search import (
    calculate_keyword_score,
    create_query_preprocessor,
    embed_notices,
    hydrate_result_notice,
)


RESET_PATTERNS = {"초기화", "처음부터", "대화 리셋", "검색 리셋"}
RETRIEVAL_MODES = {"hybrid", "keyword"}

# search.py의 검색 정책을 HTTP 챗봇에서도 동일하게 적용합니다.
TOP_K = 15
MAX_RESULT_CHOICES = 3
SEMANTIC_WEIGHT = 0.85
KEYWORD_WEIGHT = 0.15
MIN_TOP_SCORE = 0.67
MIN_KEYWORD_SCORE = 0.7
MIN_SEMANTIC_SCORE = 0.8
MAX_SEMANTIC_SCORE_GAP = 0.025
MIN_SPECIFIC_QUERY_KEYWORDS = 3
MIN_KEYWORD_COVERAGE = 0.5

RECENT_SORT_PATTERNS = (
    "최신순",
    "최신 순",
    "최근순",
    "최근 순",
    "날짜순",
    "날짜 순",
    "작성일순",
    "작성일 순",
)


def normalize_text(text: str) -> str:
    return " ".join(text.lower().split())


def search_notices(
    model: Any,
    question: str,
    notices: list[dict],
    notice_embeddings: Any,
    top_k: int = TOP_K,
    exclude_notice_ids: tuple | list | set | None = None,
    preprocessor: QueryPreprocessor = DEFAULT_PREPROCESSOR,
) -> list[dict]:
    """search.py와 같은 의미·키워드 하이브리드 점수로 공지를 검색합니다."""
    question_embedding = model.encode(
        f"query: {question}",
        normalize_embeddings=True,
    )
    question_embedding = np.asarray(question_embedding, dtype=np.float32)
    semantic_scores = notice_embeddings @ question_embedding
    excluded_ids = set(exclude_notice_ids or ())
    keywords = preprocessor.extract_keywords(question)
    results = []

    for index, notice in enumerate(notices):
        if notice.get("id") in excluded_ids:
            continue

        semantic_score = float(semantic_scores[index])
        keyword_score, matched_keywords = calculate_keyword_score(
            question=question,
            notice=notice,
            keywords=keywords,
            preprocessor=preprocessor,
        )
        hybrid_score = (
            semantic_score * SEMANTIC_WEIGHT
            + keyword_score * KEYWORD_WEIGHT
        )
        results.append({
            "score": hybrid_score,
            "hybrid_score": hybrid_score,
            "semantic_score": semantic_score,
            "keyword_score": keyword_score,
            "matched_keywords": matched_keywords,
            "notice": notice,
        })

    results.sort(key=lambda result: result["hybrid_score"], reverse=True)
    return results[: min(top_k, len(results))]


def get_relevant_notices(
    results: list[dict],
    min_top_score: float = MIN_TOP_SCORE,
    min_keyword_score: float = MIN_KEYWORD_SCORE,
    min_semantic_score: float = MIN_SEMANTIC_SCORE,
    required_keywords: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """search.py와 같은 임계점·키워드 커버리지로 후보를 확정합니다."""
    if not results:
        return []

    top_score = results[0]["hybrid_score"]
    top_keyword_score = max(result["keyword_score"] for result in results)
    top_semantic_score = max(result["semantic_score"] for result in results)

    if (
        top_score < min_top_score
        and top_keyword_score < min_keyword_score
        and top_semantic_score < min_semantic_score
    ):
        return []

    unique_required_keywords = {
        normalize_text(keyword)
        for keyword in (required_keywords or ())
        if normalize_text(keyword)
    }
    relevant_results = []

    for result in results:
        semantic_score_gap = top_semantic_score - result["semantic_score"]
        has_strong_keyword_match = (
            result["keyword_score"] >= min_keyword_score
        )
        has_strong_semantic_match = (
            result["semantic_score"] >= min_semantic_score
            and semantic_score_gap <= MAX_SEMANTIC_SCORE_GAP
        )
        if not (has_strong_keyword_match or has_strong_semantic_match):
            continue

        if len(unique_required_keywords) >= MIN_SPECIFIC_QUERY_KEYWORDS:
            matched_keywords = {
                normalize_text(keyword)
                for keyword in result.get("matched_keywords", [])
            }
            keyword_coverage = (
                len(unique_required_keywords & matched_keywords)
                / len(unique_required_keywords)
            )
            if keyword_coverage < MIN_KEYWORD_COVERAGE:
                continue

        relevant_results.append(result)

    return sort_notices_by_published_at(relevant_results)


def sort_notices_by_published_at(results: list[dict]) -> list[dict]:
    return sorted(
        results,
        key=lambda result: str(
            result.get("notice", {}).get("published_at") or ""
        ),
        reverse=True,
    )


def is_recent_sort_request(question: str) -> bool:
    normalized = " ".join(question.lower().split())
    return any(pattern in normalized for pattern in RECENT_SORT_PATTERNS)


def should_answer_without_selection(route: QueryRoute | None) -> bool:
    return route == QueryRoute.EXAM_NOTICE_SEARCH


class ChatbotConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    answer: str
    state: dict
    sources: list[dict]
    selection_required: bool = False
    has_more: bool = False


class ChatbotService:
    """CLI와 HTTP API가 함께 사용하는 한 번의 챗봇 요청 처리기입니다."""

    def __init__(
        self,
        *,
        model: Any,
        preprocessor: QueryPreprocessor,
        search_source: str,
        notice_repository: NoticeRepository,
        chunk_repository: ChunkRepository | None = None,
        notices: list[dict] | None = None,
        notice_embeddings: Any = None,
        retrieval_mode: str = "hybrid",
    ) -> None:
        self.model = model
        self.preprocessor = preprocessor
        self.search_source = search_source
        self.notice_repository = notice_repository
        self.chunk_repository = chunk_repository
        self.notices = notices or []
        self.notice_embeddings = notice_embeddings
        self.retrieval_mode = retrieval_mode

    @classmethod
    def create_default(cls) -> "ChatbotService":
        try:
            search_source = get_rag_search_source()
            retrieval_mode = os.getenv(
                "RAG_RETRIEVAL_MODE",
                "hybrid",
            ).lower()
            if retrieval_mode not in RETRIEVAL_MODES:
                raise ValueError(
                    "RAG_RETRIEVAL_MODE는 hybrid 또는 keyword여야 합니다."
                )
            if retrieval_mode == "keyword" and search_source != "chunks":
                raise ValueError(
                    "keyword 검색은 RAG_SEARCH_SOURCE=chunks에서만 사용할 수 있습니다."
                )

            notice_repository = get_notice_repository()
            chunk_repository = (
                get_chunk_repository() if search_source == "chunks" else None
            )
            model = None
            if retrieval_mode == "hybrid":
                from sentence_transformers import SentenceTransformer

                model = SentenceTransformer(EMBEDDING_MODEL_NAME)
        except Exception as error:
            raise ChatbotConfigurationError(
                f"챗봇 초기화에 실패했습니다: {error}"
            ) from error

        try:
            alias_rows = get_alias_repository().fetch_aliases()
            preprocessor = create_query_preprocessor(alias_rows)
        except AliasRepositoryError:
            preprocessor = DEFAULT_PREPROCESSOR

        notices = []
        notice_embeddings = None
        if search_source == "notices":
            try:
                notices = notice_repository.fetch_notices()
            except NoticeRepositoryError as error:
                raise ChatbotConfigurationError(str(error)) from error
            if not notices:
                raise ChatbotConfigurationError("저장된 공지가 없습니다.")
            notice_embeddings = embed_notices(
                model=model,
                notices=notices,
            )

        return cls(
            model=model,
            preprocessor=preprocessor,
            search_source=search_source,
            notice_repository=notice_repository,
            chunk_repository=chunk_repository,
            notices=notices,
            notice_embeddings=notice_embeddings,
            retrieval_mode=retrieval_mode,
        )

    def handle_message(
        self,
        message: str,
        state_snapshot: dict | None = None,
        selected_notice_id: int | str | None = None,
        load_more: bool = False,
    ) -> ChatResult:
        question = message.strip()
        if not question and selected_notice_id is None and not load_more:
            return self._result("질문을 입력해주세요.", ConversationState())

        if question in RESET_PATTERNS:
            return self._result(
                "대화 검색 상태를 초기화했습니다.",
                ConversationState(),
            )

        conversation = self._restore_state(state_snapshot or {})

        if load_more:
            return self._show_next_candidate_page(conversation)

        if selected_notice_id is not None:
            selected_result = conversation.select_candidate_by_id(
                selected_notice_id
            )
            if selected_result is None:
                return self._result(
                    "현재 검색 결과에 없는 공지입니다. 다시 검색해주세요.",
                    conversation,
                )

            selected_result = self._hydrate(selected_result)
            conversation.active_result = selected_result
            answer_question = (
                conversation.pending_answer_question
                or conversation.last_search_query
                or str(selected_result.get("notice", {}).get("title") or "공지")
            )
            answer = generate_answer(
                question=answer_question,
                relevant_results=[selected_result],
                answer_mode="focused",
            )
            return self._result(answer, conversation, [selected_result])

        selected_result, selection_error = conversation.select_candidate(question)
        if selection_error:
            return self._result(selection_error, conversation)

        if selected_result:
            selected_result = self._hydrate(selected_result)
            conversation.active_result = selected_result
            answer_question = (
                conversation.pending_answer_question
                or conversation.last_search_query
                or question
            )
            answer = generate_answer(
                question=answer_question,
                relevant_results=[selected_result],
                answer_mode="focused",
            )
            return self._result(answer, conversation, [selected_result])

        if (
            conversation.has_candidates
            and conversation.active_result is None
            and is_recent_sort_request(question)
        ):
            conversation.candidate_results = sort_notices_by_published_at(
                conversation.candidate_results
            )
            visible_count = max(
                len(conversation.shown_notice_ids),
                min(MAX_RESULT_CHOICES, len(conversation.candidate_results)),
            )
            visible_results = conversation.candidate_results[:visible_count]
            visible_ids = self._notice_ids(visible_results)
            conversation.shown_notice_ids = visible_ids
            conversation.referenced_notice_ids = visible_ids
            return self._result(
                self._create_card_selection_answer(visible_results),
                conversation,
                visible_results,
                selection_required=True,
                has_more=self._has_hidden_candidates(conversation),
            )

        processed_query = self.preprocessor.process(question)
        answer_question = processed_query.normalized

        plan = plan_question(
            question=processed_query.normalized,
            router_context=conversation.build_router_context(),
        )
        conversation.add_message("user", processed_query.normalized)
        query_route = plan.route

        if plan.route == QueryRoute.MORE_NOTICE_SEARCH:
            return self._show_next_candidate_page(conversation)

        if plan.route == QueryRoute.SELECTED_NOTICE_ANSWER:
            if conversation.active_result is None:
                return self._result(
                    "먼저 궁금한 공지를 검색하고 선택해주세요.",
                    conversation,
                    conversation.candidate_results,
                    selection_required=conversation.has_candidates,
                    has_more=self._has_hidden_candidates(conversation),
                )
            answer = generate_answer(
                question=answer_question,
                relevant_results=[conversation.active_result],
                answer_mode="focused",
            )
            return self._result(
                answer,
                conversation,
                [conversation.active_result],
            )

        if plan.route == QueryRoute.GENERAL_CHAT:
            return self._result(
                generate_general_answer(plan.search_query),
                conversation,
            )

        if plan.route == QueryRoute.CLARIFICATION:
            return self._result(
                plan.clarification
                or "어떤 종류의 공지를 찾는지 조금 더 알려주세요.",
                conversation,
            )

        intent = route_to_intent(plan.route)
        processed_query = replace(
            processed_query,
            normalized=plan.search_query,
        )

        resolution = conversation.resolve(processed_query, intent)
        if resolution.clarification:
            return self._result(resolution.clarification, conversation)

        search_results = self._search(
            resolution.search_question,
            query_route=query_route,
            exclude_notice_ids=resolution.exclude_notice_ids,
        )
        relevant_results = get_relevant_notices(
            results=search_results,
            required_keywords=self.preprocessor.extract_keywords(
                resolution.search_question
            ),
        )
        relevant_results = sort_notices_by_published_at(relevant_results)

        if not relevant_results:
            if query_route == QueryRoute.OPEN_NOTICE_SEARCH:
                answer = (
                    "현재 신청 가능한 공지를 확인하지 못했습니다. "
                    "공지의 마감일 정보가 아직 등록되지 않았을 수도 있습니다."
                )
            else:
                answer = "현재 저장된 공지에서는 관련 내용을 찾지 못했습니다."
            return self._result(answer, conversation)

        displayed_results = relevant_results[:MAX_RESULT_CHOICES]
        has_more = len(relevant_results) > len(displayed_results)
        conversation.record_results(
            resolution,
            relevant_results,
            answer_question=answer_question,
        )
        conversation.shown_notice_ids = self._notice_ids(displayed_results)
        conversation.referenced_notice_ids = self._notice_ids(displayed_results)

        if should_answer_without_selection(query_route):
            direct_results = [self._hydrate(result) for result in displayed_results]
            conversation.candidate_results = direct_results
            conversation.active_result = direct_results[0]
            answer = generate_answer(
                question=answer_question,
                relevant_results=direct_results,
                answer_mode="focused",
            )
            return self._result(answer, conversation, direct_results)

        if len(displayed_results) > 1:
            return self._result(
                self._create_card_selection_answer(displayed_results),
                conversation,
                displayed_results,
                selection_required=True,
                has_more=has_more,
            )

        active_result = self._hydrate(displayed_results[0])
        conversation.active_result = active_result
        answer = generate_answer(
            question=answer_question,
            relevant_results=[active_result],
            answer_mode="focused",
        )
        return self._result(answer, conversation, [active_result])

    def _show_next_candidate_page(
        self,
        conversation: ConversationState,
    ) -> ChatResult:
        """최초 검색에서 확정한 후보를 재검색 없이 3개씩 더 공개합니다."""
        if not conversation.has_candidates:
            return self._result(
                "먼저 궁금한 공지를 검색해주세요.",
                conversation,
            )

        visible_count = min(
            len(conversation.shown_notice_ids) + MAX_RESULT_CHOICES,
            len(conversation.candidate_results),
        )
        visible_results = conversation.candidate_results[:visible_count]
        visible_ids = self._notice_ids(visible_results)
        conversation.shown_notice_ids = visible_ids
        conversation.referenced_notice_ids = visible_ids

        has_more = visible_count < len(conversation.candidate_results)
        answer = (
            self._create_card_selection_answer(visible_results)
            if has_more
            else "임계점을 통과한 공지를 모두 보여드렸습니다. 궁금한 공지 카드를 선택해주세요."
        )
        return self._result(
            answer,
            conversation,
            visible_results,
            selection_required=True,
            has_more=has_more,
        )

    @staticmethod
    def _has_hidden_candidates(conversation: ConversationState) -> bool:
        return (
            len(conversation.shown_notice_ids)
            < len(conversation.candidate_results)
        )

    @staticmethod
    def _create_card_selection_answer(results: list[dict]) -> str:
        return (
            f"관련 공지 {len(results)}개를 찾았습니다. "
            "궁금한 공지 카드를 선택해주세요."
        )

    @staticmethod
    def _notice_ids(results: list[dict]) -> list[Any]:
        return [
            notice_id
            for result in results
            if (notice_id := result.get("notice", {}).get("id")) is not None
        ]

    def _search(
        self,
        question: str,
        *,
        query_route: QueryRoute | None,
        exclude_notice_ids: tuple | list | set,
    ) -> list[dict]:
        if self.search_source == "chunks":
            if self.chunk_repository is None:
                raise ChatbotConfigurationError(
                    "공지 청크 검색 저장소가 준비되지 않았습니다."
                )
            if self.retrieval_mode == "keyword":
                return search_notice_chunks_keyword_only(
                    question=question,
                    repository=self.chunk_repository,
                    top_k=TOP_K,
                    deadline_from=(
                        get_current_datetime().isoformat()
                        if query_route == QueryRoute.OPEN_NOTICE_SEARCH
                        else None
                    ),
                    exclude_notice_ids=exclude_notice_ids,
                    preprocessor=self.preprocessor,
                )
            return search_notice_chunks(
                model=self.model,
                question=question,
                repository=self.chunk_repository,
                top_k=TOP_K,
                semantic_weight=SEMANTIC_WEIGHT,
                keyword_weight=KEYWORD_WEIGHT,
                deadline_from=(
                    get_current_datetime().isoformat()
                    if query_route == QueryRoute.OPEN_NOTICE_SEARCH
                    else None
                ),
                exclude_notice_ids=exclude_notice_ids,
                preprocessor=self.preprocessor,
            )

        return search_notices(
            model=self.model,
            question=question,
            notices=self.notices,
            notice_embeddings=self.notice_embeddings,
            top_k=TOP_K,
            exclude_notice_ids=exclude_notice_ids,
            preprocessor=self.preprocessor,
        )

    def _hydrate(self, result: dict) -> dict:
        if self.search_source != "chunks":
            return result
        return hydrate_result_notice(result, repository=self.notice_repository)

    def _restore_state(self, snapshot: dict) -> ConversationState:
        conversation = ConversationState(
            last_search_query=snapshot.get("last_search_query"),
            referenced_notice_ids=list(
                snapshot.get("referenced_notice_ids") or []
            )[:100],
            shown_notice_ids=list(snapshot.get("shown_notice_ids") or [])[:100],
            pending_answer_question=snapshot.get("pending_answer_question"),
            router_context=list(snapshot.get("router_context") or [])[-6:],
        )

        candidate_ids = list(snapshot.get("candidate_notice_ids") or [])[:100]
        conversation.candidate_results = self._restore_results(candidate_ids)

        active_notice_id = snapshot.get("active_notice_id")
        if active_notice_id is not None:
            restored = self._restore_results([active_notice_id])
            conversation.active_result = restored[0] if restored else None
        return conversation

    def _restore_results(self, notice_ids: list[Any]) -> list[dict]:
        results = []
        seen = set()
        for notice_id in notice_ids:
            if notice_id in seen:
                continue
            seen.add(notice_id)
            notice = self.notice_repository.fetch_notice(notice_id)
            if notice is not None:
                results.append({"notice": notice})
        return results

    @staticmethod
    def _sources(results: list[dict] | None) -> list[dict]:
        sources = []
        seen = set()
        for result in results or []:
            notice = result.get("notice") or {}
            source_id = notice.get("id")
            if source_id in seen:
                continue
            seen.add(source_id)
            sources.append({
                "id": source_id,
                "title": notice.get("title") or "제목 없음",
                "publishedAt": notice.get("published_at"),
                "url": notice.get("url"),
            })
        return sources

    def _result(
        self,
        answer: str,
        conversation: ConversationState,
        results: list[dict] | None = None,
        selection_required: bool = False,
        has_more: bool = False,
    ) -> ChatResult:
        conversation.add_message("assistant", answer[:400])
        return ChatResult(
            answer=answer,
            state=conversation.snapshot(),
            sources=self._sources(results),
            selection_required=selection_required,
            has_more=has_more,
        )
