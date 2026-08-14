import os
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

LLM_MODEL_NAME = "gemini-3.5-flash"
_client: genai.Client | None = None


class NoticeCandidateDecision(BaseModel):
    mode: str = Field(pattern="^(answer|list|not_found)$")
    notice_ids: list[int | str] = Field(default_factory=list)
    reason: str = ""


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


def create_candidate_context(results: list[dict]) -> str:
    """판별기에 전달할 검색 후보를 길이 제한과 함께 직렬화합니다."""
    parts = []
    for result in results:
        notice = result.get("notice") or {}
        content = " ".join(str(notice.get("content") or "").split())[:2500]
        parts.append(
            "\n".join([
                f"[공지 ID: {notice.get('id')}]",
                f"제목: {notice.get('title', '')}",
                f"카테고리: {notice.get('category', '')}",
                f"게시일: {notice.get('published_at', '')}",
                f"마감일: {notice.get('deadline', '')}",
                f"검색된 본문: {content}",
            ])
        )
    return "\n\n".join(parts)


def judge_notice_candidates(
    question: str,
    search_query: str,
    candidates: list[dict],
    router_context: str = "",
    now: datetime | None = None,
    client: Any | None = None,
) -> NoticeCandidateDecision:
    """검색 상위 후보에서 실제 관련 공지와 다음 UI 동작을 판정합니다."""
    if not candidates:
        return NoticeCandidateDecision(mode="not_found")

    current_datetime = now or datetime.now(ZoneInfo("Asia/Seoul"))
    candidate_context = create_candidate_context(candidates)
    prompt = f"""
당신은 공지 검색 결과의 관련성을 최종 판정하는 시스템입니다.
검색 점수나 후보 순위를 정답으로 간주하지 말고 공지의 제목과 본문을 직접 읽으세요.
후보에 존재하는 공지 ID만 반환하세요.

[판정 모드]
- answer: 사용자가 날짜, 장소, 신청 방법, IP, 특정 공지 요약처럼 구체적인 답을
  요구하며, 선택한 공지 본문으로 바로 답할 수 있음
- list: 장학금 공지, 대회, 모집처럼 관련 공지 목록 자체를 요청함
- not_found: 어떤 후보도 질문과 직접 관련이 없거나 후보 본문으로 답할 수 없음

[규칙]
1. 단어가 비슷하다는 이유만으로 관련 있다고 판정하지 마세요.
2. answer는 질문에 답하는 데 필요한 최소 공지만 선택하세요.
3. list는 질문 주제에 실제 해당하는 공지를 빠짐없이 선택하세요.
4. "공지 알려줘", "뭐 있어?", "목록 보여줘"는 목록 요청입니다. 현재 신청 가능,
   모집 중, 마감 전이라는 표현이 없다면 마감 여부로 제외하지 마세요.
5. 목록 요청에서는 제목이 질문의 주제와 직접 일치하는 공지를 관련 공지로
   인정하세요. 공지의 주목적이 질문 주제여야 하며, 본문이나 제목의 괄호에 해당
   단어가 부수적인 조건·참고사항으로만 등장하는 공지는 제외하세요. 본문에 질문의
   구체적인 답이 있어야 할 필요는 없습니다.
6. 현재 신청 가능 여부가 중요하면 현재 시각과 마감일·본문을 확인하세요.
7. 과거 학기와 현재 학기 공지가 섞이면 질문에 맞는 학기를 선택하세요. 질문이
   학기를 제한하지 않은 목록 요청이면 관련된 여러 학기 공지를 선택할 수 있습니다.
8. 관련 공지가 하나도 없으면 반드시 not_found와 빈 notice_ids를 반환하세요.

[현재 시각]
{current_datetime.isoformat()} (Asia/Seoul)

[최근 대화와 상태]
{router_context or "없음"}

[현재 사용자 질문]
{question}

[검색용으로 해석된 질문]
{search_query}

[검색 후보]
{candidate_context}
""".strip()

    try:
        response = (client or get_client()).models.generate_content(
            model=LLM_MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=NoticeCandidateDecision,
            ),
        )
        parsed = getattr(response, "parsed", None)
        if parsed is None:
            if not response.text:
                raise ValueError("후보 판별기가 빈 응답을 반환했습니다.")
            decision = NoticeCandidateDecision.model_validate_json(response.text)
        else:
            decision = NoticeCandidateDecision.model_validate(parsed)
    except Exception:
        # 판별기 장애가 검색 전체 장애로 번지지 않도록 후보 목록을 그대로 제공합니다.
        return NoticeCandidateDecision(
            mode="list",
            notice_ids=[result.get("notice", {}).get("id") for result in candidates],
            reason="candidate_judge_fallback",
        )

    valid_ids = {
        str(result.get("notice", {}).get("id"))
        for result in candidates
        if result.get("notice", {}).get("id") is not None
    }
    selected_ids = []
    for notice_id in decision.notice_ids:
        if str(notice_id) in valid_ids and str(notice_id) not in {
            str(existing) for existing in selected_ids
        }:
            selected_ids.append(notice_id)

    if decision.mode == "not_found" or not selected_ids:
        return NoticeCandidateDecision(
            mode="not_found",
            reason=decision.reason,
        )

    return NoticeCandidateDecision(
        mode=decision.mode,
        notice_ids=selected_ids,
        reason=decision.reason,
    )


def _friendly_llm_error(error: Exception) -> str:
    """LLM 호출 실패를 사용자용 안내 문구로 바꿉니다.

    Gemini 사용량(무료 쿼터)을 다 쓴 429/RESOURCE_EXHAUSTED 상황에서 원문 에러
    (JSON 덤프) 대신 안내를 보여줍니다.
    """
    text = str(error)
    is_quota = (
        getattr(error, "code", None) == 429
        or "RESOURCE_EXHAUSTED" in text
        or "quota" in text.lower()
    )
    if is_quota:
        return (
            "지금은 챗봇 사용량이 많아 답변을 드릴 수 없어요. "
            "잠시 후 다시 질문해 주세요. 🙏"
        )
    return "답변을 생성하는 중 문제가 발생했어요. 잠시 후 다시 질문해 주세요."


def generate_general_answer(
    resolved_question: str,
    now: datetime | None = None,
) -> str:
    """공지 검색이 필요 없는 짧은 대화에 답변합니다."""
    current_datetime = now or datetime.now(ZoneInfo("Asia/Seoul"))
    prompt = f"""
당신은 홍익대학교 컴퓨터공학과 공지사항 안내 챗봇입니다.
사용자의 인사나 감사에는 자연스럽고 짧게 답하세요.
공지와 무관한 지식이나 작업을 요청하면 공지 검색을 도와줄 수 있다고 안내하세요.
현재 시각은 {current_datetime.isoformat()}, 시간대는 Asia/Seoul입니다.

[사용자 질문]
{resolved_question}
""".strip()

    try:
        response = get_client().models.generate_content(
            model=LLM_MODEL_NAME,
            contents=prompt,
        )
    except Exception as error:
        return _friendly_llm_error(error)

    if not response.text:
        return "안녕하세요. 찾고 싶은 공지 내용을 말씀해주세요."

    return response.text.strip()


def generate_answer(
    question: str,
    resolved_question: str,
    relevant_results: list[dict],
    answer_mode: str = "focused",
    now: datetime | None = None,
    client: Any | None = None,
) -> str:
    """검색된 공지를 근거로 사용자 질문에 답변합니다."""
    if not relevant_results:
        return "현재 저장된 공지에서는 관련 내용을 찾지 못했습니다."

    context = create_context(relevant_results)
    current_datetime = now or datetime.now(ZoneInfo("Asia/Seoul"))
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
10. 시험 날짜, 시간, 장소 질문은 정확히 일치하는 과목 행을 찾아 해당 값을 먼저
    말하고, 공지 전체 요약으로 바꾸지 마세요.
11. 사용자가 특정 학기, 연도, 과목, 교수 등을 명시했다면 그 조건을 반드시 우선하세요.
    사용자가 학기를 지정하지 않았을 때만 현재 시각과 공지 작성일을 기준으로
    가장 최근 학기의 정보를 우선하세요.
12. 답변 생성 단계에서는 사용자의 원본 표현, 약어, 은어를 새롭게 해석하거나
    다른 과목명·교수명으로 확장하지 마세요.
    시스템이 제공한 "질문 해석"이 있다면 그것을 최종적으로 확정된 질문으로 간주하세요.
13. 원본 사용자 질문과 "질문 해석"이 다르게 보이더라도,
    반드시 "질문 해석"의 과목명, 교수명, 학기, 질문 유형을 기준으로 답하세요.
14. 시험 공지에서 과목을 찾을 때는 "질문 해석"에 명시된 과목명 또는 교수명과
    일치하는 행만 사용할 수 있습니다.
    유사한 이름의 다른 과목 행은 사용하지 마세요.

[현재 시각]
{current_datetime.isoformat()} (Asia/Seoul)

[원본 사용자 질문]
{question}

[질문 해석]
{resolved_question}

[검색된 공지]
{context}
""".strip()

    try:
        response = (client or get_client()).models.generate_content(
            model=LLM_MODEL_NAME,
            contents=prompt,
        )
    except Exception as error:
        return _friendly_llm_error(error)

    if not response.text:
        return "답변을 생성하지 못했습니다."

    return append_source_section(
        answer=response.text,
        results=relevant_results,
    )
