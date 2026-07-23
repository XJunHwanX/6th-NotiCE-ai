from dataclasses import replace

import numpy as np
from sentence_transformers import SentenceTransformer

if __package__:
    from .config import EMBEDDING_MODEL_NAME
    from .conversation import ConversationState
    from .db import (
        AliasRepositoryError,
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
    from .retriever import search_notice_chunks
    from .router import (
        QueryRoute,
        get_current_datetime,
        plan_question,
        route_to_intent,
    )
else:
    from config import EMBEDDING_MODEL_NAME
    from conversation import ConversationState
    from db import (
        AliasRepositoryError,
        ChunkRepositoryError,
        NoticeRepository,
        NoticeRepositoryError,
        get_alias_repository,
        get_chunk_repository,
        get_notice_repository,
        get_rag_search_source,
    )
    from intent import QueryIntent, classify_intent
    from llm import generate_answer, generate_general_answer
    from preprocess import DEFAULT_PREPROCESSOR, QueryPreprocessor
    from retriever import search_notice_chunks
    from router import (
        QueryRoute,
        get_current_datetime,
        plan_question,
        route_to_intent,
    )


# =========================================================
# 기본 설정
# =========================================================

# 검색할 최대 공지 개수
TOP_K = 5

# 첫 응답에서 사용자가 고를 수 있도록 보여줄 최대 공지 수
MAX_RESULT_CHOICES = 3

# 하이브리드 검색 가중치
SEMANTIC_WEIGHT = 0.75
KEYWORD_WEIGHT = 0.25

# 검색 결과 1위가 이 점수보다 낮으면 관련 없는 질문으로 판단
MIN_TOP_SCORE = 0.67

# 정확 키워드가 충분히 맞으면 의미 점수가 낮아도 관련 공지로 판단
MIN_KEYWORD_SCORE = 0.6

# 1위 결과와 점수 차이가 이 값보다 큰 공지는 제외
MAX_SCORE_GAP = 0.07

# 구체적인 질문은 전체 핵심어 중 절반 이상이 실제 공지에 등장해야 함
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

# =========================================================
# 데이터 불러오기
# =========================================================

def load_notices() -> list[dict]:
    """환경 설정에 따라 Supabase 또는 샘플 JSON에서 공지를 불러옵니다."""
    return get_notice_repository().fetch_notices()


def create_notice_text(notice: dict) -> str:
    """
    공지의 제목, 카테고리, 작성일, 본문을
    하나의 검색용 문자열로 합칩니다.
    """
    return (
        f"제목: {notice.get('title', '')}\n"
        f"카테고리: {notice.get('category') or ''}\n"
        f"작성일: {notice.get('published_at', '')}\n"
        f"내용: {notice.get('content', '')}"
    )


# =========================================================
# 키워드 검색
# =========================================================

def normalize_text(text: str) -> str:
    """키워드 비교를 위해 대소문자와 공백을 정리합니다."""
    return " ".join(text.lower().split())


def extract_keywords(
    question: str,
    preprocessor: QueryPreprocessor = DEFAULT_PREPROCESSOR,
) -> list[str]:
    """사용자 질문에서 키워드 검색에 사용할 단어를 추출합니다."""
    return preprocessor.extract_keywords(question)


def calculate_keyword_score(
    question: str,
    notice: dict,
    keywords: list[str] | None = None,
    preprocessor: QueryPreprocessor = DEFAULT_PREPROCESSOR,
) -> tuple[float, list[str]]:
    """
    질문 키워드가 공지 제목/카테고리/본문에 얼마나 직접 등장하는지 계산합니다.

    제목과 카테고리에 등장한 키워드는 본문보다 조금 더 높은 점수를 줍니다.
    """
    if keywords is None:
        keywords = extract_keywords(question, preprocessor=preprocessor)

    if not keywords:
        return 0.0, []

    title_text = normalize_text(str(notice.get("title", "")))
    category_text = normalize_text(str(notice.get("category", "")))
    content_text = normalize_text(str(notice.get("content", "")))
    url_text = normalize_text(str(notice.get("url", "")))

    matched_keywords = []
    score = 0.0

    for keyword in keywords:
        keyword_score = 0.0

        if keyword in title_text:
            keyword_score += 1.0

        if keyword in category_text:
            keyword_score += 0.8

        if keyword in content_text:
            keyword_score += 0.6

        if keyword in url_text:
            keyword_score += 0.2

        if keyword_score > 0:
            matched_keywords.append(keyword)
            score += min(keyword_score, 1.0)

    return score / len(keywords), matched_keywords


# =========================================================
# 임베딩 생성
# =========================================================

def embed_notices(
    model: SentenceTransformer,
    notices: list[dict],
) -> np.ndarray:
    """모든 공지를 임베딩 벡터로 변환합니다."""
    notice_texts = [
        f"passage: {create_notice_text(notice)}"
        for notice in notices
    ]

    embeddings = model.encode(
        notice_texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=True,
    )

    return np.asarray(
        embeddings,
        dtype=np.float32,
    )


# =========================================================
# 공지 검색
# =========================================================

def search_notices(
    model: SentenceTransformer,
    question: str,
    notices: list[dict],
    notice_embeddings: np.ndarray,
    top_k: int = TOP_K,
    exclude_notice_ids: tuple | list | set | None = None,
    preprocessor: QueryPreprocessor = DEFAULT_PREPROCESSOR,
) -> list[dict]:
    """
    의미 검색과 키워드 검색을 함께 사용해 관련 공지를 반환합니다.
    """
    question_embedding = model.encode(
        f"query: {question}",
        normalize_embeddings=True,
    )

    question_embedding = np.asarray(
        question_embedding,
        dtype=np.float32,
    )

    results = []
    excluded_ids = set(exclude_notice_ids or ())
    keywords = extract_keywords(question, preprocessor=preprocessor)

    # 모든 벡터가 정규화되어 있으므로 내적 결과가 코사인 유사도와 같음
    semantic_scores = notice_embeddings @ question_embedding

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
    max_score_gap: float = MAX_SCORE_GAP,
    required_keywords: list[str] | tuple[str, ...] | None = None,
) -> list[dict]:
    """
    검색 결과 중 질문과 관련성이 충분한 공지들을 반환합니다.

    1. 검색 결과 1위 점수가 너무 낮으면 전체 검색 실패
    2. 1위 점수와 차이가 크지 않은 공지들을 함께 선택
    """
    if not results:
        return []

    top_score = results[0]["hybrid_score"]

    top_keyword_score = results[0]["keyword_score"]

    # 하이브리드 점수와 키워드 점수가 모두 낮으면 관련 공지 없음
    if top_score < min_top_score and top_keyword_score < min_keyword_score:
        return []

    relevant_results = []
    unique_required_keywords = {
        normalize_text(keyword)
        for keyword in (required_keywords or ())
        if normalize_text(keyword)
    }

    for result in results:
        score = result["hybrid_score"]
        score_gap = top_score - score

        if (
            score_gap <= max_score_gap
            or result["keyword_score"] >= min_keyword_score
        ):
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
    """관련도 순서를 날짜가 같은 공지의 보조 기준으로 유지하며 최신순 정렬합니다."""
    return sorted(
        results,
        key=lambda result: str(
            result.get("notice", {}).get("published_at") or ""
        ),
        reverse=True,
    )


def is_recent_sort_request(question: str) -> bool:
    """현재 검색 결과를 최신순으로 다시 보여달라는 요청인지 확인합니다."""
    normalized = " ".join(question.lower().split())
    return any(pattern in normalized for pattern in RECENT_SORT_PATTERNS)


def create_result_selection_answer(results: list[dict]) -> str:
    """본문을 노출하지 않고 선택 가능한 공지 제목 목록을 만듭니다."""
    lines = [f"관련 공지 {len(results)}개를 찾았습니다.", ""]

    for index, result in enumerate(results, start=1):
        notice = result["notice"]
        title = notice.get("title") or "제목 없음"
        lines.append(f"{index}. {title}")

    lines.extend([
        "",
        "궁금한 공지의 번호나 제목을 입력해주세요. 예: 1번",
    ])
    return "\n".join(lines)


def create_query_preprocessor(alias_rows: list[dict]) -> QueryPreprocessor:
    aliases = {
        str(row["alias"]): str(row["meaning"])
        for row in alias_rows
    }
    return QueryPreprocessor(aliases=aliases)


def hydrate_result_notice(
    result: dict,
    repository: NoticeRepository,
) -> dict:
    """선택된 검색 결과의 부분 청크를 공지 전체 본문으로 교체합니다."""
    notice_id = result.get("notice", {}).get("id")

    if notice_id is None:
        return result

    full_notice = repository.fetch_notice(notice_id)

    if full_notice is None:
        return result

    return {
        **result,
        "notice": full_notice,
    }


def should_answer_without_selection(route: QueryRoute | None) -> bool:
    """사용자 질문에 바로 답해야 하는 검색 경로인지 반환합니다."""
    return route == QueryRoute.EXAM_NOTICE_SEARCH


# =========================================================
# 결과 출력
# =========================================================

def print_search_failure(results: list[dict]) -> None:
    """관련 공지를 찾지 못했을 때 검색 정보를 출력합니다."""
    print("\n관련 공지를 찾지 못했습니다.")

    if not results:
        return

    top_score = results[0]["hybrid_score"]
    print(f"최고 하이브리드 점수: {top_score:.4f}")
    print(f"의미 검색 점수: {results[0]['semantic_score']:.4f}")
    print(f"키워드 검색 점수: {results[0]['keyword_score']:.4f}")

    if len(results) >= 2:
        second_score = results[1]["hybrid_score"]
        score_gap = top_score - second_score

        print(f"2위 하이브리드 점수: {second_score:.4f}")
        print(f"1위와 2위 점수 차이: {score_gap:.4f}")


# =========================================================
# 프로그램 실행
# =========================================================

def main() -> None:
    notices = []
    notice_embeddings = None
    chunk_repository = None

    try:
        search_source = get_rag_search_source()
        notice_repository = get_notice_repository()

        if search_source == "chunks":
            chunk_repository = get_chunk_repository()
    except (NoticeRepositoryError, ChunkRepositoryError) as error:
        print(f"챗봇 실행 설정을 확인해주세요: {error}")
        return

    print("임베딩 모델을 불러오는 중입니다.")

    try:
        model = SentenceTransformer(EMBEDDING_MODEL_NAME)
    except Exception as error:
        print(f"임베딩 모델을 불러오지 못했습니다: {error}")
        return

    try:
        alias_rows = get_alias_repository().fetch_aliases()
        preprocessor = create_query_preprocessor(alias_rows)
        print(f"은어 사전 {len(alias_rows)}개를 불러왔습니다.")
    except AliasRepositoryError as error:
        preprocessor = DEFAULT_PREPROCESSOR
        print(f"은어 사전을 불러오지 못해 기본 검색으로 진행합니다: {error}")

    if search_source == "chunks":
        print("Supabase notice_chunks RPC 검색 모드입니다.")
    else:
        notices = notice_repository.fetch_notices()

        if not notices:
            print("저장된 공지가 없습니다.")
            return

        print(
            f"{notice_repository.source_name}에서 "
            f"공지 {len(notices)}개를 불러왔습니다."
        )
        print("공지 임베딩을 생성합니다.")

        notice_embeddings = embed_notices(
            model=model,
            notices=notices,
        )

        print("임베딩 생성 완료")
        print(f"임베딩 배열 크기: {notice_embeddings.shape}")

    conversation = ConversationState()

    while True:
        try:
            question = input(
                "\n질문을 입력하세요. 종료하려면 exit 입력: "
            ).strip()
        except EOFError:
            print("\n입력이 종료되어 프로그램을 종료합니다.")
            break

        if question.lower() == "exit":
            print("프로그램을 종료합니다.")
            break

        if not question:
            print("질문을 입력해주세요.")
            continue

        selected_result, selection_error = conversation.select_candidate(question)

        if selection_error:
            print(f"\n===== 챗봇 답변 =====\n{selection_error}")
            continue

        if selected_result:
            if search_source == "chunks":
                try:
                    selected_result = hydrate_result_notice(
                        selected_result,
                        repository=notice_repository,
                    )
                    conversation.active_result = selected_result
                except NoticeRepositoryError as error:
                    print(f"공지 전체 본문을 불러오지 못했습니다: {error}")

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
            print("\n===== 챗봇 답변 =====")
            print(answer)
            continue

        if (
            conversation.has_candidates
            and conversation.active_result is None
            and is_recent_sort_request(question)
        ):
            sorted_results = sort_notices_by_published_at(
                conversation.candidate_results
            )
            conversation.candidate_results = sorted_results
            print("\n===== 챗봇 답변 =====")
            print(create_result_selection_answer(sorted_results))
            continue

        processed_query = preprocessor.process(question)
        answer_question = processed_query.normalized

        if processed_query.resolved_aliases:
            resolved_text = ", ".join(
                f"{match.alias} → {match.meaning}"
                for match in processed_query.resolved_aliases
            )
            print(f"은어 해석: {resolved_text}")
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
            print("\n===== 챗봇 답변 =====")
            print(answer)
            continue

        if (
            conversation.has_candidates
            and conversation.active_result is None
            and rule_intent in {QueryIntent.FOLLOW_UP, QueryIntent.NOTICE_SUMMARY}
        ):
            print(
                "\n===== 챗봇 답변 =====\n"
                "먼저 궁금한 공지의 번호나 제목을 선택해주세요."
            )
            continue

        query_route = None

        if rule_intent == QueryIntent.MORE_RESULTS:
            intent = rule_intent
        elif rule_intent == QueryIntent.NOTICE_SUMMARY:
            print(
                "\n===== 챗봇 답변 =====\n"
                "요약할 공지를 먼저 검색하거나 선택해주세요."
            )
            continue
        else:
            plan = plan_question(
                question=processed_query.normalized,
                has_context=conversation.has_context,
                has_active_notice=conversation.active_result is not None,
            )
            query_route = plan.route
            route_source = "LLM" if plan.source == "llm" else "기본 규칙"
            print(f"질문 경로: {plan.route.value} ({route_source})")

            if plan.route == QueryRoute.SELECTED_NOTICE_ANSWER:
                if conversation.active_result is None:
                    print(
                        "\n===== 챗봇 답변 =====\n"
                        "먼저 궁금한 공지를 검색하고 선택해주세요."
                    )
                    continue

                answer = generate_answer(
                    question=answer_question,
                    relevant_results=[conversation.active_result],
                    answer_mode="focused",
                )
                print("\n===== 챗봇 답변 =====")
                print(answer)
                continue

            if plan.route == QueryRoute.GENERAL_CHAT:
                answer = generate_general_answer(plan.search_query)
                print("\n===== 챗봇 답변 =====")
                print(answer)
                continue

            if plan.route == QueryRoute.CLARIFICATION:
                clarification = plan.clarification or (
                    "어떤 종류의 공지를 찾는지 조금 더 알려주세요."
                )
                print(f"\n===== 챗봇 답변 =====\n{clarification}")
                continue

            intent = route_to_intent(plan.route)
            processed_query = replace(
                processed_query,
                normalized=plan.search_query,
            )

        resolution = conversation.resolve(processed_query, intent)

        if intent == QueryIntent.MORE_RESULTS:
            answer_question = resolution.search_question

        if resolution.clarification:
            print(f"\n===== 챗봇 답변 =====\n{resolution.clarification}")
            continue

        if resolution.search_question != question:
            print(f"질문 해석: {resolution.search_question}")

        try:
            if search_source == "chunks":
                search_results = search_notice_chunks(
                    model=model,
                    question=resolution.search_question,
                    repository=chunk_repository,
                    top_k=TOP_K,
                    semantic_weight=SEMANTIC_WEIGHT,
                    keyword_weight=KEYWORD_WEIGHT,
                    deadline_from=(
                        get_current_datetime().isoformat()
                        if query_route == QueryRoute.OPEN_NOTICE_SEARCH
                        else None
                    ),
                    exclude_notice_ids=resolution.exclude_notice_ids,
                    preprocessor=preprocessor,
                )
            else:
                search_results = search_notices(
                    model=model,
                    question=resolution.search_question,
                    notices=notices,
                    notice_embeddings=notice_embeddings,
                    top_k=TOP_K,
                    exclude_notice_ids=resolution.exclude_notice_ids,
                    preprocessor=preprocessor,
                )
        except ChunkRepositoryError as error:
            print(f"\n청크 검색을 사용할 수 없습니다: {error}")
            print(
                "DB 준비 전에는 RAG_SEARCH_SOURCE=notices로 실행해주세요."
            )
            continue

        relevant_results = get_relevant_notices(
            results=search_results,
            required_keywords=preprocessor.extract_keywords(
                resolution.search_question
            ),
        )

        if not relevant_results:
            if resolution.intent == QueryIntent.MORE_RESULTS:
                print("\n현재 저장된 공지 중 추가 결과가 없습니다.")
                continue

            if query_route == QueryRoute.OPEN_NOTICE_SEARCH:
                print(
                    "\n현재 신청 가능한 공지를 확인하지 못했습니다. "
                    "크롤링 파이프라인의 notices.deadline 적재 상태를 "
                    "확인해주세요."
                )
                continue

            print_search_failure(search_results)
            continue

        displayed_results = relevant_results[:MAX_RESULT_CHOICES]
        conversation.record_results(
            resolution,
            displayed_results,
            answer_question=answer_question,
        )

        if should_answer_without_selection(query_route):
            direct_results = displayed_results

            if search_source == "chunks":
                try:
                    direct_results = [
                        hydrate_result_notice(
                            result,
                            repository=notice_repository,
                        )
                        for result in displayed_results
                    ]
                except NoticeRepositoryError as error:
                    print(f"공지 전체 본문을 불러오지 못했습니다: {error}")

            conversation.candidate_results = direct_results
            conversation.active_result = direct_results[0]
            answer = generate_answer(
                question=answer_question,
                relevant_results=direct_results,
                answer_mode="focused",
            )
            print("\n===== 챗봇 답변 =====")
            print(answer)
            continue

        if len(displayed_results) > 1:
            print("\n===== 챗봇 답변 =====")
            print(create_result_selection_answer(displayed_results))
            continue

        active_result = displayed_results[0]

        if search_source == "chunks":
            try:
                active_result = hydrate_result_notice(
                    active_result,
                    repository=notice_repository,
                )
            except NoticeRepositoryError as error:
                print(f"공지 전체 본문을 불러오지 못했습니다: {error}")

        conversation.active_result = active_result

        answer = generate_answer(
            question=answer_question,
            relevant_results=[active_result],
            answer_mode="focused",
        )

        print("\n===== 챗봇 답변 =====")
        print(answer)

if __name__ == "__main__":
    main()
