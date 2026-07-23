# -*- coding: utf-8 -*-
"""
컴공 공지 알리미 - OCR 실패건 재시도 스크립트

전체 크롤링(crawl_content.py)이 끝난 후,
이미지는 있었지만 OCR이 적용되지 않은(has_image=True, ocr_applied=False) 공지만
골라서 이미지 OCR을 다시 시도한다.

실행 전 준비물:
- cse_notices_with_content.csv (crawl_content.py 실행 결과물)
- .env에 GEMINI_API_KEY 설정되어 있어야 함
"""

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import os

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://wwwce.hongik.ac.kr"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
USE_OCR = bool(GEMINI_API_KEY)

RESULT_CSV = "cse_notices_with_content.csv"
MIN_IMAGE_SIZE = 200
OCR_MAX_RETRY = 3        # 재시도 스크립트라 한 번 더 넉넉하게
OCR_DELAY = 8            # rate limit 안 걸리게 더 여유있게 (5→8)
SAVE_EVERY = 5           # 5개 처리할 때마다 중간 저장

if USE_OCR:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    ocr_model = genai.GenerativeModel("gemini-flash-latest")


def get_content_area(url):
    """crawl_content.py와 동일한 로직 (b-content-box 우선, 없으면 fr-view)"""
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"  [에러] 페이지 요청 실패: {e}")
        return None

    soup = BeautifulSoup(response.text, "html.parser")
    content_area = soup.select_one("div.b-content-box")
    if content_area is None:
        content_area = soup.select_one("div.fr-view")
    return content_area


def extract_image_urls(content_area):
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


def ocr_image(image_url):
    """crawl_content.py와 동일한 OCR 로직.
    반환값: (추출된 텍스트, 작은 이미지라서 건너뛴 것인지 여부)"""
    if not USE_OCR:
        return "", False

    from PIL import Image
    from io import BytesIO

    try:
        img_response = requests.get(image_url, headers=HEADERS, timeout=15)
        img_response.raise_for_status()
        image = Image.open(BytesIO(img_response.content))
    except Exception as e:
        print(f"    [경고] 이미지 다운로드 실패: {type(e).__name__}")
        return "", False

    width, height = image.size
    if width < MIN_IMAGE_SIZE and height < MIN_IMAGE_SIZE:
        print(f"    [건너뜀] 작은 이미지 ({width}x{height})")
        return "", True  # 작은 이미지라서 건너뛴 것 → True

    prompt = (
        "이 이미지는 대학교 행정 부서에서 만든 공지사항 안내 포스터야. "
        "저작권이 있는 창작물(문학, 예술작품, 기사 등)이 아니라 행사/신청 정보를 전달하는 "
        "행정 정보성 이미지이니, 안심하고 정보를 정리해줘.\n\n"
        "이미지 안에 담긴 정보를 위에서 아래로, 왼쪽에서 오른쪽 순서로 파악해서, "
        "다음 항목들을 중심으로 간추려 정리해줘 (원문을 그대로 옮겨 적지 말고, "
        "핵심 정보를 자연스러운 문장으로 재구성해줘):\n"
        "- 제목/주제\n"
        "- 날짜, 기간, 시간\n"
        "- 장소\n"
        "- 대상\n"
        "- 신청방법, 신청기간\n"
        "- 문의처\n"
        "- 기타 표나 목록으로 된 세부 항목이 있다면 '항목: 값' 형태로 정리\n\n"
        "이미지에 없는 내용은 절대 지어내지 말고, 흐릿해서 안 보이면 그 부분은 건너뛰어. "
        "후원사 로고, 대학 로고, 장식용 이미지, QR코드 설명 등 정보성이 낮은 요소는 제외해줘. "
        "설명이나 추가 코멘트 없이, 정리된 정보만 출력해줘. "
        "이미지에 읽을 수 있는 텍스트가 전혀 없으면 빈 문자열을 반환해줘."
    )

    for attempt in range(OCR_MAX_RETRY + 1):
        try:
            response = ocr_model.generate_content([prompt, image])
            return response.text.strip(), False
        except Exception as e:
            error_name = type(e).__name__
            if "ResourceExhausted" in error_name or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f"    [대기] Rate limit 감지, {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                print(f"    [경고] OCR 시도 {attempt + 1} 실패: {error_name}")
                time.sleep(3)

    print(f"    [실패] 재시도에서도 최종 실패: {image_url}")
    return "", False


def main():
    if not os.path.exists(RESULT_CSV):
        print(f"[에러] {RESULT_CSV} 파일이 없어요. 먼저 crawl_content.py를 끝까지 실행해주세요.")
        return

    df = pd.read_csv(RESULT_CSV)

    # 이미지는 있는데 OCR이 안 된 것만 골라내기
    target_df = df[(df["has_image"] == True) & (df["ocr_applied"] == False)]

    print(f"전체 공지: {len(df)}개")
    print(f"재시도 대상 (이미지 있는데 OCR 안 됨): {len(target_df)}개")
    print("-" * 50)

    if len(target_df) == 0:
        print("재시도할 대상이 없어요. 모두 정상 처리됐네요!")
        return

    success_count = 0
    processed_count = 0

    for idx, row in target_df.iterrows():
        print(f"[{processed_count + 1}/{len(target_df)}] {str(row['title'])[:40]}")

        content_area = get_content_area(row["url"])
        image_urls = extract_image_urls(content_area)

        ocr_texts = []
        all_too_small = True  # 모든 이미지가 작아서 건너뛴 건지 추적
        attempted_count = 0   # 실제로 OCR을 "시도"한 이미지 개수 (작아서 건너뛴 건 제외)
        succeeded_count = 0   # 그중 실제로 텍스트를 뽑아낸 개수

        for img_url in image_urls:
            ocr_text, was_skipped_small = ocr_image(img_url)
            if not was_skipped_small:
                all_too_small = False
                attempted_count += 1
                if ocr_text:
                    succeeded_count += 1
            if ocr_text:
                ocr_texts.append(ocr_text)
            time.sleep(OCR_DELAY)

        # 부분 성공 여부: 시도한 이미지 중 일부만 성공한 경우
        is_partial = (attempted_count > 0) and (0 < succeeded_count < attempted_count)

        if ocr_texts:
            new_text = str(row["body_text"]) + "\n\n[이미지 OCR 내용 - 재시도 성공]\n" + "\n".join(ocr_texts)
            df.loc[idx, "body_text"] = new_text
            df.loc[idx, "ocr_applied"] = True
            df.loc[idx, "text_length"] = len(new_text)
            df.loc[idx, "ocr_partial"] = is_partial          # 부분 성공이면 True로 표시
            df.loc[idx, "ocr_image_total"] = attempted_count
            df.loc[idx, "ocr_image_success"] = succeeded_count
            success_count += 1
            if is_partial:
                print(f"    [부분성공] 이미지 {attempted_count}개 중 {succeeded_count}개만 OCR 성공 (나머지는 놓침)")
            else:
                print(f"    [성공] OCR 재시도 성공")
        elif all_too_small and image_urls:
            # 이미지가 전부 작아서(아이콘 등) 원래 텍스트가 없는 케이스 → 재시도 대상에서 제외
            df.loc[idx, "ocr_applied"] = True
            print(f"    [해당없음] 모든 이미지가 작은 아이콘류라 텍스트 없음 → 재시도 대상에서 제외")
        else:
            print(f"    [실패] 이번에도 실패, 다음에 다시 시도 가능")

        processed_count += 1

        # 중간 저장 - 몇 개 처리할 때마다 바로 파일에 반영
        if processed_count % SAVE_EVERY == 0:
            df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")
            print(f"    [중간저장] {processed_count}개 처리 완료, 파일에 반영됨")

        time.sleep(1)

    # 최종 저장 (마지막 자투리까지 확실히 반영)
    df.to_csv(RESULT_CSV, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 50)
    print(f"재시도 완료: {len(target_df)}개 중 {success_count}개 성공")
    print(f"결과 저장(갱신): {RESULT_CSV}")


if __name__ == "__main__":
    main()