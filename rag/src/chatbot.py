from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any

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
from .intent import QueryIntent, classify_intent
from .llm import generate_answer, generate_general_answer
from .preprocess import DEFAULT_PREPROCESSOR, QueryPreprocessor
from .retriever import (
    search_notice_chunks,
    search_notice_chunks_keyword_only,
)
from .router import QueryRoute, get_current_datetime, plan_question, route_to_intent
from .search import (
    KEYWORD_WEIGHT,
    MAX_RESULT_CHOICES,
    SEMANTIC_WEIGHT,
    TOP_K,
    create_query_preprocessor,
    create_result_selection_answer,
    embed_notices,
    get_relevant_notices,
    hydrate_result_notice,
    is_recent_sort_request,
    search_notices,
    should_answer_without_selection,
    sort_notices_by_published_at,
)


RESET_PATTERNS = {"초기화", "처음부터", "대화 리셋", "검색 리셋"}
RETRIEVAL_MODES = {"hybrid", "keyword"}


class ChatbotConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ChatResult:
    answer: str
    state: dict
    sources: list[dict]


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
    ) -> ChatResult:
        question = message.strip()
        if not question:
            return self._result("질문을 입력해주세요.", ConversationState())

        if question in RESET_PATTERNS:
            return self._result(
                "대화 검색 상태를 초기화했습니다.",
                ConversationState(),
            )

        conversation = self._restore_state(state_snapshot or {})

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
            return self._result(
                create_result_selection_answer(conversation.candidate_results),
                conversation,
                conversation.candidate_results,
            )

        processed_query = self.preprocessor.process(question)
        answer_question = processed_query.normalized
        rule_intent = classify_intent(
            processed_query.normalized,
            has_context=conversation.has_context,
        )

        if (
            conversation.active_result
            and rule_intent in {QueryIntent.FOLLOW_UP, QueryIntent.NOTICE_SUMMARY}
        ):
            answer = generate_answer(
                question=processed_query.normalized,
                relevant_results=[conversation.active_result],
                answer_mode="focused",
            )
            return self._result(
                answer,
                conversation,
                [conversation.active_result],
            )

        if (
            conversation.has_candidates
            and conversation.active_result is None
            and rule_intent in {QueryIntent.FOLLOW_UP, QueryIntent.NOTICE_SUMMARY}
        ):
            return self._result(
                "먼저 궁금한 공지의 번호나 제목을 선택해주세요.",
                conversation,
                conversation.candidate_results,
            )

        query_route = None
        if rule_intent == QueryIntent.MORE_RESULTS:
            intent = rule_intent
        elif rule_intent == QueryIntent.NOTICE_SUMMARY:
            return self._result(
                "요약할 공지를 먼저 검색하거나 선택해주세요.",
                conversation,
            )
        else:
            plan = plan_question(
                question=processed_query.normalized,
                router_context=conversation.build_router_context(),
            )
            conversation.add_message("user", processed_query.normalized)
            query_route = plan.route

            if plan.route == QueryRoute.SELECTED_NOTICE_ANSWER:
                if conversation.active_result is None:
                    return self._result(
                        "먼저 궁금한 공지를 검색하고 선택해주세요.",
                        conversation,
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
        if intent == QueryIntent.MORE_RESULTS:
            answer_question = resolution.search_question

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

        if not relevant_results:
            if resolution.intent == QueryIntent.MORE_RESULTS:
                answer = "현재 저장된 공지 중 추가 결과가 없습니다."
            elif query_route == QueryRoute.OPEN_NOTICE_SEARCH:
                answer = (
                    "현재 신청 가능한 공지를 확인하지 못했습니다. "
                    "공지의 마감일 정보가 아직 등록되지 않았을 수도 있습니다."
                )
            else:
                answer = "현재 저장된 공지에서는 관련 내용을 찾지 못했습니다."
            return self._result(answer, conversation)

        displayed_results = relevant_results[:MAX_RESULT_CHOICES]
        conversation.record_results(
            resolution,
            displayed_results,
            answer_question=answer_question,
        )

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
                create_result_selection_answer(displayed_results),
                conversation,
                displayed_results,
            )

        active_result = self._hydrate(displayed_results[0])
        conversation.active_result = active_result
        answer = generate_answer(
            question=answer_question,
            relevant_results=[active_result],
            answer_mode="focused",
        )
        return self._result(answer, conversation, [active_result])

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
            )[:MAX_RESULT_CHOICES],
            shown_notice_ids=list(snapshot.get("shown_notice_ids") or [])[:20],
            pending_answer_question=snapshot.get("pending_answer_question"),
            router_context=list(snapshot.get("router_context") or [])[-6:],
        )

        candidate_ids = list(snapshot.get("candidate_notice_ids") or [])[
            :MAX_RESULT_CHOICES
        ]
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
    ) -> ChatResult:
        conversation.add_message("assistant", answer[:400])
        return ChatResult(
            answer=answer,
            state=conversation.snapshot(),
            sources=self._sources(results),
        )
