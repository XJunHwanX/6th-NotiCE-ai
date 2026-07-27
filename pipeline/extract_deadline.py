"""
공지 본문에서 마감일(신청/제출 마감)을 추출합니다.
Gemini를 사용해 자연어 표현(다양한 날짜/시간 포맷)을 하나의 날짜시간으로 정규화합니다.

- 마감 시간이 본문에 명시되어 있으면 그 시간을 그대로 사용합니다.
- 마감 시간이 명시되어 있지 않고 날짜만 있으면 그날 23:59로 간주합니다.
- 마감일이 없거나 불명확한 공지는 None을 반환합니다.

반환 형식: "YYYY-MM-DD HH:MM:SS+09:00" (한국 시간대 명시)
"""

import re
from datetime import datetime


def extract_deadline(title: str, content: str, published_at: str, ocr_model) -> str | None:
    """
    공지 제목/본문에서 마감일을 추출해 timestamptz 호환 문자열로 반환합니다.

    Args:
        title: 공지 제목
        content: 본문 텍스트 (표/OCR 포함)
        published_at: 공지 게시일 ('YYYY-MM-DD' 형식) - 연도 추론 기준으로 사용
        ocr_model: pipeline.py에서 이미 생성된 Gemini 모델 인스턴스 재사용

    Returns:
        "YYYY-MM-DD HH:MM:SS+09:00" 형식 문자열, 또는 마감일이 없으면 None
    """
    if ocr_model is None:
        return None

    excerpt = content[:1500] if content else ""

    prompt = f"""
다음은 대학교 공지사항입니다. 이 공지에서 "학생이 신청/제출을 위해 행동해야 하는 가장 이른 마감일시"를 찾아주세요.

규칙:
- 마감일과 마감 시간이 함께 명시되어 있으면 반드시 "YYYY-MM-DD HH:MM" 형식으로 답해주세요. (예: 2026-07-30 17:00)
- 마감 시간이 명시되어 있지 않고 날짜만 있으면 "YYYY-MM-DD 23:59" 형식으로 답해주세요. (그날 자정 직전으로 간주)
- 연도가 명시 안 되어 있으면, 공지 게시일({published_at})을 기준으로 가장 가까운 미래 날짜로 추론하세요.
- 전형 절차가 여러 단계면(예: 서류 접수 마감, 면접 일정, 최종 발표일), 그중 학생이 신청서/서류를 제출해야 하는 가장 빠른 마감일시(접수 마감)를 사용하세요. 면접 날짜나 발표일은 마감일이 아닙니다.
- 마감일이 아예 없거나 "채용시까지", "상시모집"처럼 특정 날짜가 아니면 "없음"이라고만 답해주세요.
- 다른 설명 없이 날짜시간 또는 "없음"만 출력하세요.

[공지 제목]
{title}

[공지 게시일]
{published_at}

[공지 본문]
{excerpt}
""".strip()

    try:
        response = ocr_model.generate_content(prompt)
        result = response.text.strip()
    except Exception as e:
        print(f"   [경고] 마감일 추출 실패: {e}")
        return None

    if "없음" in result or not result:
        return None

    # YYYY-MM-DD HH:MM 패턴 추출 (시간까지 명시된 경우)
    match = re.search(r"(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", result)

    if match:
        date_str = match.group(1)
        time_str = match.group(2)
    else:
        # 시간 없이 날짜만 반환된 경우 대비 (fallback)
        date_only_match = re.search(r"(\d{4}-\d{2}-\d{2})", result)
        if not date_only_match:
            return None
        date_str = date_only_match.group(1)
        time_str = "23:59"

    datetime_str = f"{date_str} {time_str}:00"

    # 유효한 날짜시간인지 검증
    try:
        datetime.strptime(datetime_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None

    # 한국 시간대(KST, UTC+9) 명시하여 반환
    return f"{datetime_str}+09:00"