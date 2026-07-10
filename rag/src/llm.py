import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    raise ValueError(
        "GEMINI_API_KEY를 찾을 수 없습니다. "
        "레포 최상위의 .env 파일을 확인해주세요."
    )

client = genai.Client(api_key=api_key)

LLM_MODEL_NAME = "gemini-3.5-flash"


def create_context(results: list[dict]) -> str:
    """검색된 공지 여러 개를 LLM에 전달할 텍스트로 만듭니다."""
    context_parts = []

    for index, result in enumerate(results, start=1):
        notice = result["notice"]

        context_parts.append(
            f"""
[공지 {index}]
제목: {notice.get("title", "")}
카테고리: {notice.get("category", "")}
작성일: {notice.get("posted_at", "")}
내용: {notice.get("content", "")}
원문 URL: {notice.get("url", "")}
검색 유사도: {result.get("score", 0):.4f}
""".strip()
        )

    return "\n\n".join(context_parts)


def generate_answer(
    question: str,
    relevant_results: list[dict],
) -> str:
    """검색된 공지를 근거로 사용자 질문에 답변합니다."""
    if not relevant_results:
        return "현재 저장된 공지에서는 관련 내용을 찾지 못했습니다."

    context = create_context(relevant_results)

    prompt = f"""
당신은 홍익대학교 컴퓨터공학과 공지사항 안내 챗봇입니다.

반드시 아래 검색된 공지 내용만 근거로 답변하세요.

답변 규칙:
1. 공지에 없는 내용은 추측하지 마세요.
2. 사용자의 질문에 직접 필요한 내용만 간단하고 정확하게 답하세요.
3. 질문에 해당하는 공지가 여러 개라면 번호 목록으로 정리하세요.
4. 날짜, 시간, 대상, 신청 방법, 지원 조건을 정확하게 전달하세요.
5. 검색된 공지 중 질문과 직접 관련 없는 공지는 답변에서 제외하세요.
6. 공지 내용만으로 답할 수 없다면 확인할 수 없다고 말하세요.
7. 답변 마지막에는 실제로 참고한 공지의 제목과 URL을 표시하세요.

[사용자 질문]
{question}

[검색된 공지]
{context}
""".strip()

    try:
        response = client.models.generate_content(
            model=LLM_MODEL_NAME,
            contents=prompt,
        )
    except Exception as error:
        return f"답변 생성 중 오류가 발생했습니다: {error}"

    if not response.text:
        return "답변을 생성하지 못했습니다."

    return response.text.strip()