import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


# search.py 위치를 기준으로 rag 폴더 경로 계산
RAG_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = RAG_DIR / "data" / "sample_notices.json"

MODEL_NAME = "intfloat/multilingual-e5-small"


def load_notices() -> list[dict]:
    """JSON 파일에서 샘플 공지를 불러옵니다."""
    with DATA_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


def create_notice_text(notice: dict) -> str:
    """공지의 제목, 카테고리, 본문을 하나의 검색용 문자열로 합칩니다."""
    return (
        f"제목: {notice['title']}\n"
        f"카테고리: {notice['category']}\n"
        f"내용: {notice['content']}"
    )


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

    return np.asarray(embeddings, dtype=np.float32)


def search_notices(
    model: SentenceTransformer,
    question: str,
    notices: list[dict],
    notice_embeddings: np.ndarray,
    top_k: int = 3,
) -> list[dict]:
    """질문과 의미가 가장 비슷한 공지를 반환합니다."""
    question_embedding = model.encode(
        f"query: {question}",
        normalize_embeddings=True,
    )

    question_embedding = np.asarray(
        question_embedding,
        dtype=np.float32,
    )

    # 벡터를 정규화했기 때문에 내적으로 코사인 유사도를 계산할 수 있음
    similarities = notice_embeddings @ question_embedding

    top_indices = np.argsort(similarities)[::-1][:top_k]

    results = []

    for index in top_indices:
        results.append({
            "score": float(similarities[index]),
            "notice": notices[index],
        })

    return results

MIN_SIMILARITY = 0.84
MIN_SCORE_MARGIN = 0.03


def is_relevant_result(results: list[dict]) -> bool:
    """검색 결과가 질문과 충분히 관련 있는지 판단합니다."""
    if not results:
        return False

    top_score = results[0]["score"]

    if top_score < MIN_SIMILARITY:
        return False

    if len(results) >= 2:
        second_score = results[1]["score"]
        score_margin = top_score - second_score

        if score_margin < MIN_SCORE_MARGIN:
            return False

    return True

def print_results(results: list[dict]) -> None:
    print("\n===== 검색 결과 =====")

    for rank, result in enumerate(results, start=1):
        notice = result["notice"]

        print(f"\n{rank}. {notice['title']}")
        print(f"카테고리: {notice['category']}")
        print(f"유사도: {result['score']:.4f}")
        print(f"작성일: {notice['posted_at']}")
        print(f"내용: {notice['content']}")
        print(f"URL: {notice['url']}")


def main() -> None:
    print("임베딩 모델을 불러오는 중입니다.")

    model = SentenceTransformer(MODEL_NAME)

    notices = load_notices()

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

        results = search_notices(
            model=model,
            question=question,
            notices=notices,
            notice_embeddings=notice_embeddings,
            top_k=3,
        )
        if not is_relevant_result(results):
            print("\n관련 공지를 찾지 못했습니다.")

            if results:
                top_score = results[0]["score"]
                print(f"최고 유사도: {top_score:.4f}")

            if len(results) >= 2:
                 second_score = results[1]["score"]
                 margin = top_score - second_score
                 print(f"1위와 2위 점수 차이: {margin:.4f}")

            continue
        print_results(results)


if __name__ == "__main__":
    main()