import json
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

# 검색 결과 1위가 이 점수보다 낮으면 관련 없는 질문으로 판단
MIN_TOP_SCORE = 0.84

# 1위 결과와 점수 차이가 이 값보다 큰 공지는 제외
MAX_SCORE_GAP = 0.04


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
    질문과 의미가 비슷한 공지를 검색하고
    유사도가 높은 순서대로 반환합니다.
    """
    question_embedding = model.encode(
        f"query: {question}",
        normalize_embeddings=True,
    )

    question_embedding = np.asarray(
        question_embedding,
        dtype=np.float32,
    )

    # 모든 벡터가 정규화되어 있으므로
    # 내적 결과가 코사인 유사도와 같음
    similarities = notice_embeddings @ question_embedding

    result_count = min(top_k, len(notices))

    top_indices = np.argsort(similarities)[::-1][:result_count]

    results = []

    for index in top_indices:
        results.append({
            "score": float(similarities[index]),
            "notice": notices[index],
        })

    return results


def get_relevant_notices(
    results: list[dict],
    min_top_score: float = MIN_TOP_SCORE,
    max_score_gap: float = MAX_SCORE_GAP,
) -> list[dict]:
    """
    검색 결과 중 질문과 관련성이 충분한 공지들을 반환합니다.

    1. 검색 결과 1위 점수가 너무 낮으면 전체 검색 실패
    2. 1위 점수와 차이가 크지 않은 공지들을 함께 선택
    """
    if not results:
        return []

    top_score = results[0]["score"]

    # 가장 높은 결과조차 기준보다 낮으면 관련 공지 없음
    if top_score < min_top_score:
        return []

    relevant_results = []

    for result in results:
        score = result["score"]
        score_gap = top_score - score

        if score_gap <= max_score_gap:
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
        print(f"유사도: {result['score']:.4f}")
        print(f"작성일: {notice.get('posted_at', '없음')}")
        print(f"내용: {notice.get('content', '없음')}")
        print(f"URL: {notice.get('url', '없음')}")


def print_search_failure(results: list[dict]) -> None:
    """관련 공지를 찾지 못했을 때 검색 정보를 출력합니다."""
    print("\n관련 공지를 찾지 못했습니다.")

    if not results:
        return

    top_score = results[0]["score"]
    print(f"최고 유사도: {top_score:.4f}")

    if len(results) >= 2:
        second_score = results[1]["score"]
        score_gap = top_score - second_score

        print(f"2위 유사도: {second_score:.4f}")
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