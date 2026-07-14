# -*- coding: utf-8 -*-
"""
 본문 크롤러 (A 담당)

개선 사항:
1. 중간 저장 (10개마다 임시 저장 → 중간에 멈춰도 결과 보존)
2. 이미 처리한 공지는 건너뛰기 (이어서 실행 가능)
3. OCR 실패 시 재시도 (일시적 오류 대응)
4. Rate Limit 대응 (429 에러 시 더 오래 대기)
5. 작은 이미지 필터링 (아이콘/로고 OCR 방지)

실행 전 준비물:
- cse_notices.csv (article_no, title, url, date 컬럼 필요)
- (OCR용) Gemini API 키
"""

from dotenv import load_dotenv
load_dotenv()  # .env 파일을 읽어서 환경변수로 등록
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import os

# ============================================
# 설정
# ============================================
HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://wwwce.hongik.ac.kr"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
USE_OCR = bool(GEMINI_API_KEY)


# 조정 가능한 설정값들
INPUT_CSV = "../data/cse_notices.csv"
OUTPUT_CSV = "cse_notices_with_content.csv"
SAVE_EVERY = 10          # 몇 개마다 중간 저장할지
OCR_MAX_RETRY = 2        # OCR 실패 시 재시도 횟수
MIN_IMAGE_SIZE = 200     # 이 픽셀(가로 or 세로)보다 작은 이미지는 OCR 건너뜀
PAGE_DELAY = 1           # 공지 간 대기 시간(초)
OCR_DELAY = 3            # OCR 호출 간 대기 시간(초) - rate limit 여유있게

if USE_OCR:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    ocr_model = genai.GenerativeModel("gemini-flash-latest")


# ============================================
# 1. 상세 페이지에서 본문 영역 가져오기
# ============================================
def get_content_area(url):
    """공지 상세 페이지 URL을 받아서 본문 영역 BeautifulSoup 객체를 반환.
    일부 공지는 div.fr-view 밖에 본문(<p>)이 붙어있는 경우가 있어서,
    더 상위 컨테이너인 div.b-content-box를 우선 사용하고,
    없으면 div.fr-view로 대체한다."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [에러] 페이지 요청 실패: {e}")
        return None
 
    soup = BeautifulSoup(response.text, "html.parser")
 
    # b-content-box가 fr-view의 부모 컨테이너라 더 안전함 (예외 케이스 포함)
    content_area = soup.select_one("div.b-content-box")
    if content_area is None:
        content_area = soup.select_one("div.fr-view")
 
    return content_area


# ============================================
# 2. 텍스트 추출
# ============================================
def extract_text(content_area):
    """본문에서 텍스트 추출"""
    if content_area is None:
        return ""
    text = content_area.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


# ============================================
# 3. HTML 표 추출
# ============================================
def extract_tables(content_area):
    """진짜 HTML table 태그를 찾아서 '항목: 값' 문장으로 변환"""
    if content_area is None:
        return ""

    tables = content_area.find_all("table")
    if not tables:
        return ""

    from io import StringIO
    all_texts = []
    for table in tables:
        try:
            df_list = pd.read_html(StringIO(str(table)))
            if not df_list:
                continue
            df = df_list[0]
            for _, row in df.iterrows():
                row_text = ", ".join(
                    f"{col}: {val}" for col, val in row.items() if pd.notna(val)
                )
                if row_text:
                    all_texts.append(row_text)
        except Exception as e:
            print(f"  [경고] 표 파싱 실패 (건너뜀): {type(e).__name__}")
            continue

    return "\n".join(all_texts)


# ============================================
# 4. 이미지 URL 수집
# ============================================
def extract_image_urls(content_area):
    """본문 안의 이미지 URL 목록 반환 (상대경로 → 절대경로)"""
    if content_area is None:
        return []

    urls = []
    for img in content_area.find_all("img"):
        src = img.get("src", "")
        if not src:
            continue
        if src.startswith("/"):
            src = BASE_URL + src
        urls.append(src)
    return urls


# ============================================
# 5. 이미지 OCR (재시도 + 크기 필터 + rate limit 대응)
# ============================================
def ocr_image(image_url):
    """이미지 URL을 Gemini에 넘겨서 텍스트 추출"""
    if not USE_OCR:
        return ""

    from PIL import Image
    from io import BytesIO

    # 이미지 다운로드
    try:
        img_response = requests.get(image_url, headers=HEADERS, timeout=15)
        img_response.raise_for_status()
        image = Image.open(BytesIO(img_response.content))
    except Exception as e:
        print(f"  [경고] 이미지 다운로드 실패: {type(e).__name__}")
        return ""

    # 작은 이미지(아이콘/로고 등)는 건너뛰기
    width, height = image.size
    if width < MIN_IMAGE_SIZE and height < MIN_IMAGE_SIZE:
        print(f"  [건너뜀] 작은 이미지 ({width}x{height})")
        return ""

    prompt = (
         "이 이미지는 대학교 공지사항에 첨부된 이미지야. "
        "이미지 안의 모든 텍스트를 위에서 아래로, 왼쪽에서 오른쪽 순서로 읽어서 추출해줘.\n"
        "규칙:\n"
        "- 제목, 날짜, 기간, 시간, 장소, 대상, 신청방법, 문의처 같은 핵심 정보는 반드시 포함해줘.\n"
        "- 표가 있으면 각 행의 내용을 자연스러운 문장이나 '항목: 값' 형태로 정리해줘.\n"
        "- 목록이면 목록 구조를 유지해줘.\n"
        "- 이미지에 없는 내용은 절대 지어내지 말고, 흐릿해서 안 보이면 그 부분은 건너뛰어.\n"
        "- 후원사 로고, 대학 로고, 장식용 이미지 등 의미 없는 나열은 추출하지 않아도 돼.\n"
        "- 설명이나 요약 없이 추출된 텍스트만 출력해줘.\n"
        "- 이미지에 읽을 수 있는 텍스트가 전혀 없으면 빈 문자열을 반환해줘."
    )

    # 재시도 로직
    for attempt in range(OCR_MAX_RETRY + 1):
        try:
            response = ocr_model.generate_content([prompt, image])
            return response.text.strip()
        except Exception as e:
            error_name = type(e).__name__
            # rate limit 에러면 더 오래 대기 후 재시도
            if "ResourceExhausted" in error_name or "429" in str(e):
                wait = 30 * (attempt + 1)  # 30초, 60초로 점점 늘림
                print(f"  [대기] Rate limit 감지, {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                print(f"  [경고] OCR 시도 {attempt + 1} 실패: {error_name}")
                time.sleep(3)

    print(f"  [실패] OCR 최종 실패: {image_url}")
    return ""


# ============================================
# 6. 통합 추출 함수
# ============================================
def extract_full_content(url):
    """공지 하나의 본문을 텍스트+표+이미지OCR까지 통합"""
    content_area = get_content_area(url)

    if content_area is None:
        return {
            "body_text": "", "has_table": False, "has_image": False,
            "image_count": 0, "ocr_applied": False,
        }

    text = extract_text(content_area)

    table_text = extract_tables(content_area)
    has_table = bool(table_text)
    if has_table:
        text += "\n\n[표 내용]\n" + table_text

    image_urls = extract_image_urls(content_area)
    has_image = len(image_urls) > 0
    ocr_applied = False

    if has_image and USE_OCR:
        ocr_texts = []
        for img_url in image_urls:
            ocr_text = ocr_image(img_url)
            if ocr_text:
                ocr_texts.append(ocr_text)
                ocr_applied = True
            time.sleep(OCR_DELAY)
        if ocr_texts:
            text += "\n\n[이미지 OCR 내용]\n" + "\n".join(ocr_texts)

    return {
        "body_text": text.strip(),
        "has_table": has_table,
        "has_image": has_image,
        "image_count": len(image_urls),
        "ocr_applied": ocr_applied,
    }


# ============================================
# 7. 메인 실행부 (중간저장 + 이어하기)
# ============================================
def main():
    if not os.path.exists(INPUT_CSV):
        print(f"[에러] {INPUT_CSV} 파일이 없어요.")
        return

    df = pd.read_csv(INPUT_CSV)

    # 이미 처리한 결과가 있으면 불러와서 이어하기
    done_article_nos = set()
    results = []
    if os.path.exists(OUTPUT_CSV):
        prev = pd.read_csv(OUTPUT_CSV)
        results = prev.to_dict("records")
        done_article_nos = set(prev["article_no"].astype(str))
        print(f"기존 결과 {len(results)}개 발견 → 이어서 진행")

    print(f"총 {len(df)}개 공지 중 처리 시작")
    print(f"OCR 사용 여부: {'켜짐' if USE_OCR else '꺼짐 (API 키 없음)'}")
    print("-" * 50)

    for idx, row in df.iterrows():
        article_no = str(row.get("article_no", ""))

        # 이미 처리한 건 건너뛰기
        if article_no in done_article_nos:
            continue

        print(f"[{idx + 1}/{len(df)}] {str(row['title'])[:40]}")

        content = extract_full_content(row["url"])

        results.append({
            "article_no": row.get("article_no", ""),
            "title": row["title"],
            "url": row["url"],
            "date": row.get("date", ""),
            "body_text": content["body_text"],
            "has_table": content["has_table"],
            "has_image": content["has_image"],
            "image_count": content["image_count"],
            "ocr_applied": content["ocr_applied"],
            "text_length": len(content["body_text"]),
        })

        # 중간 저장
        if len(results) % SAVE_EVERY == 0:
            pd.DataFrame(results).to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")
            print(f"  [중간저장] {len(results)}개 저장됨")

        time.sleep(PAGE_DELAY)

    # 최종 저장
    result_df = pd.DataFrame(results)
    result_df.to_csv(OUTPUT_CSV, index=False, encoding="utf-8-sig")

    # 통계
    print("\n" + "=" * 50)
    print("크롤링 완료! 통계:")
    print(f"  총 공지: {len(result_df)}개")
    print(f"  본문 텍스트 있음: {(result_df['text_length'] > 0).sum()}개")
    print(f"  표 포함: {result_df['has_table'].sum()}개")
    print(f"  이미지 포함: {result_df['has_image'].sum()}개")
    print(f"  OCR 적용됨: {result_df['ocr_applied'].sum()}개")
    print(f"  본문 완전히 비어있음: {(result_df['text_length'] == 0).sum()}개")
    print(f"\n결과 저장: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()