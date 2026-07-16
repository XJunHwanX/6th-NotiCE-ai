import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

LLM_MODEL_NAME = "gemini-3.5-flash"
_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Gemini 클라이언트를 필요할 때 한 번만 생성합니다."""
    global _client

    if _client is not None:
        return _client

    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise ValueError(
            "GEMINI_API_KEY를 찾을 수 없습니다. "
            "레포 최상위의 .env 파일을 확인해주세요."
        )

    _client = genai.Client(api_key=api_key)
    return _client


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
작성일: {notice.get("published_at", "")}
내용: {notice.get("content", "")}
원문 URL: {notice.get("url", "")}
""".strip()
        )

    return "\n\n".join(context_parts)


def create_source_section(results: list[dict]) -> str:
    """답변 아래에 붙일 출처 목록을 만듭니다."""
    source_lines = ["\n\n[참고한 공지]"]
    seen_sources = set()

    for result in results:
        notice = result["notice"]
        source_key = notice.get("url") or notice.get("id") or notice.get("title")

        if source_key in seen_sources:
            continue

        seen_sources.add(source_key)
        title = notice.get("title", "제목 없음")
        published_at = notice.get("published_at", "작성일 없음")
        url = notice.get("url", "URL 없음")

        source_lines.append(f"- {title} ({published_at})")
        source_lines.append(f"  {url}")

    return "\n".join(source_lines)


def append_source_section(answer: str, results: list[dict]) -> str:
    """LLM이 출처를 빠뜨려도 코드에서 항상 출처를 붙입니다."""
    return f"{answer.strip()}{create_source_section(results)}"


def generate_answer(
    question: str,
    relevant_results: list[dict],
    answer_mode: str = "focused",
) -> str:
    """검색된 공지를 근거로 사용자 질문에 답변합니다."""
    if not relevant_results:
        return "현재 저장된 공지에서는 관련 내용을 찾지 못했습니다."

    context = create_context(relevant_results)
    mode_instruction = (
        "선택한 공지의 목적을 한 문장으로 설명하고, 핵심 정보만 최대 4개의 "
        "짧은 항목으로 요약하세요."
        if answer_mode == "summary"
        else "질문에 대한 답을 먼저 말하고, 필요한 근거만 최대 4개의 짧은 항목으로 답하세요."
    )

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
7. 출처 목록은 시스템이 별도로 붙이므로 답변 본문에는 URL 목록을 반복하지 마세요.
8. 공지 원문 전체를 옮기거나 긴 문단으로 답하지 마세요.
9. {mode_instruction}

[사용자 질문]
{question}

[검색된 공지]
{context}
""".strip()

    try:
        response = get_client().models.generate_content(
            model=LLM_MODEL_NAME,
            contents=prompt,
        )
    except Exception as error:
        return f"답변 생성 중 오류가 발생했습니다: {error}"

    if not response.text:
        return "답변을 생성하지 못했습니다."

    return append_source_section(
        answer=response.text,
        results=relevant_results,
    )
