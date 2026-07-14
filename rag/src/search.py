import json
import re
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from llm import generate_answer


# =========================================================
# 기본 설정
# =========================================================

# search.py를 기준으로 rag 폴더 경로 계산
RAG_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = RAG_DIR / "data" / "sample_notices.json"

# 로컬에서 실행할 다국어 임베딩 모델
MODEL_NAME = "intfloat/multilingual-e5-small"

# 검색할 최대 공지 개수
TOP_K = 5

# 하이브리드 검색 가중치
SEMANTIC_WEIGHT = 0.75
KEYWORD_WEIGHT = 0.25

# 검색 결과 1위가 이 점수보다 낮으면 관련 없는 질문으로 판단
MIN_TOP_SCORE = 0.67

# 정확 키워드가 충분히 맞으면 의미 점수가 낮아도 관련 공지로 판단
MIN_KEYWORD_SCORE = 0.6

# 1위 결과와 점수 차이가 이 값보다 큰 공지는 제외
MAX_SCORE_GAP = 0.07

# 한국어 조사를 포함한 짧은 질문 표현은 키워드 검색에서 제외
STOPWORDS = {
    "공지",
    "관련",
    "알려줘",
    "알려주세요",
    "뭐야",
    "뭔가요",
    "뭐",
    "무엇",
    "무슨",
    "언제",
    "언제야",
    "언제까지",
    "언제까지야",
    "언제인가요",
    "어디",
    "어디야",
    "어딘가요",
    "어떻게",
    "있어",
    "있나요",
    "해줘",
    "해주세요",
    "나는",
    "제가",
}

KOREAN_SUFFIXES = (
    "까지",
    "부터",
    "에서",
    "에게",
    "으로",
    "하고",
    "처럼",
    "보다",
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "에",
    "로",
    "와",
    "과",
    "도",
    "만",
    "요",
)


# =========================================================
# 데이터 불러오기
# =========================================================

def load_notices() -> list[dict]:
    """JSON 파일에서 샘플 공지를 불러옵니다."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"공지 데이터 파일을 찾을 수 없습니다: {DATA_PATH}"
        )

    with DATA_PATH.open("r", encoding="utf-8") as file:
        notices = json.load(file)

    if not isinstance(notices, list):
        raise ValueError("공지 데이터는 JSON 배열 형태여야 합니다.")

    return notices


def create_notice_text(notice: dict) -> str:
    """
    공지의 제목, 카테고리, 작성일, 본문을
    하나의 검색용 문자열로 합칩니다.
    """
    return (
        f"제목: {notice.get('title', '')}\n"
        f"카테고리: {notice.get('category', '')}\n"
        f"작성일: {notice.get('posted_at', '')}\n"
        f"내용: {notice.get('content', '')}"
    )


# =========================================================
# 키워드 검색
# =========================================================

def normalize_text(text: str) -> str:
    """키워드 비교를 위해 대소문자와 공백을 정리합니다."""
    return " ".join(text.lower().split())


def strip_korean_suffix(token: str) -> str:
    """질문 키워드 끝에 붙은 대표적인 한국어 조사를 제거합니다."""
    for suffix in KOREAN_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix) + 1:
            return token[: -len(suffix)]

    return token


def extract_keywords(question: str) -> list[str]:
    """사용자 질문에서 키워드 검색에 사용할 단어를 추출합니다."""
    tokens = re.findall(r"[0-9a-zA-Z가-힣]+", question.lower())
    keywords = []

    for token in tokens:
        keyword = strip_korean_suffix(token)

        if keyword in STOPWORDS:
            continue

        if len(keyword) < 2 and not keyword.isdigit():
            continue

        if keyword not in keywords:
            keywords.append(keyword)

    return keywords


def calculate_keyword_score(
    question: str,
    notice: dict,
) -> tuple[float, list[str]]:
    """
    질문 키워드가 공지 제목/카테고리/본문에 얼마나 직접 등장하는지 계산합니다.

    제목과 카테고리에 등장한 키워드는 본문보다 조금 더 높은 점수를 줍니다.
    """
    keywords = extract_keywords(question)

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

    # 모든 벡터가 정규화되어 있으므로 내적 결과가 코사인 유사도와 같음
    semantic_scores = notice_embeddings @ question_embedding

    for index, notice in enumerate(notices):
        semantic_score = float(semantic_scores[index])
        keyword_score, matched_keywords = calculate_keyword_score(
            question=question,
            notice=notice,
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

    for result in results:
        score = result["hybrid_score"]
        score_gap = top_score - score

        if (
            score_gap <= max_score_gap
            or result["keyword_score"] >= min_keyword_score
        ):
            relevant_results.append(result)

    return relevant_results


# =========================================================
# 결과 출력
# =========================================================

def print_relevant_results(results: list[dict]) -> None:
    """관련성이 있다고 판단된 공지들을 출력합니다."""
    print("\n===== 관련 공지 검색 결과 =====")
    print(f"관련 공지 {len(results)}개를 찾았습니다.")

    for rank, result in enumerate(results, start=1):
        notice = result["notice"]

        print(f"\n{rank}. {notice.get('title', '제목 없음')}")
        print(f"카테고리: {notice.get('category', '없음')}")
        print(f"하이브리드 점수: {result['hybrid_score']:.4f}")
        print(f"의미 검색 점수: {result['semantic_score']:.4f}")
        print(f"키워드 검색 점수: {result['keyword_score']:.4f}")
        print(f"매칭 키워드: {', '.join(result['matched_keywords']) or '없음'}")
        print(f"작성일: {notice.get('posted_at', '없음')}")
        print(f"내용: {notice.get('content', '없음')}")
        print(f"URL: {notice.get('url', '없음')}")


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
    print("임베딩 모델을 불러오는 중입니다.")

    model = SentenceTransformer(MODEL_NAME)

    notices = load_notices()

    if not notices:
        print("저장된 공지가 없습니다.")
        return

    print(f"공지 {len(notices)}개를 불러왔습니다.")
    print("공지 임베딩을 생성합니다.")

    notice_embeddings = embed_notices(
        model=model,
        notices=notices,
    )

    print("임베딩 생성 완료")
    print(f"임베딩 배열 크기: {notice_embeddings.shape}")

    while True:
        question = input(
            "\n질문을 입력하세요. 종료하려면 exit 입력: "
        ).strip()

        if question.lower() == "exit":
            print("프로그램을 종료합니다.")
            break

        if not question:
            print("질문을 입력해주세요.")
            continue

        search_results = search_notices(
            model=model,
            question=question,
            notices=notices,
            notice_embeddings=notice_embeddings,
            top_k=TOP_K,
        )

        relevant_results = get_relevant_notices(
            results=search_results,
        )

        if not relevant_results:
            print_search_failure(search_results)
            continue

        print_relevant_results(relevant_results)
        
        answer = generate_answer(
            question=question,
            relevant_results=relevant_results,
        )

        print("\n===== 챗봇 답변 =====")
        print(answer)

if __name__ == "__main__":
    main()
