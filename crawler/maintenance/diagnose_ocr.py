# -*- coding: utf-8 -*-
"""
컴공 공지 알리미 - 특정 공지 OCR 진단 스크립트

특정 공지 하나의 이미지들을 개별적으로 테스트해서,
정확히 어떤 이미지가, 어떤 에러로 실패하는지 상세히 보여준다.
(rate limit 에러인지, 콘텐츠 정책 문제인지, 다운로드 실패인지 등을 구분)
"""

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup
import pandas as pd
import os

HEADERS = {"User-Agent": "Mozilla/5.0"}
BASE_URL = "https://wwwce.hongik.ac.kr"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

if not GEMINI_API_KEY:
    print("[에러] GEMINI_API_KEY가 설정되어 있지 않아요.")
    exit()

import google.generativeai as genai
genai.configure(api_key=GEMINI_API_KEY)
ocr_model = genai.GenerativeModel("gemini-flash-latest")

# 찾을 공지 제목의 일부 (여기만 바꿔서 다른 공지도 진단 가능)
TARGET_TITLE_KEYWORD = "2024-2학기 교내 신용카드수수료장학금"
RESULT_CSV = "cse_notices_with_content.csv"


def get_content_area(url):
    response = requests.get(url, headers=HEADERS, timeout=10)
    response.raise_for_status()
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


def diagnose_image(image_url, index):
    """이미지 하나에 대해 다운로드부터 OCR까지 단계별로 진단하며 상세 로그 출력"""
    from PIL import Image
    from io import BytesIO

    print(f"\n--- 이미지 {index} 진단 ---")
    print(f"URL: {image_url}")

    # 1단계: 다운로드
    try:
        img_response = requests.get(image_url, headers=HEADERS, timeout=15)
        img_response.raise_for_status()
        print(f"다운로드: 성공 (용량 {len(img_response.content) / 1024:.1f} KB)")
    except Exception as e:
        print(f"다운로드: 실패 - {type(e).__name__}: {e}")
        return

    # 2단계: 이미지 열기
    try:
        image = Image.open(BytesIO(img_response.content))
        print(f"이미지 열기: 성공 (크기 {image.size[0]}x{image.size[1]}, 포맷 {image.format})")
    except Exception as e:
        print(f"이미지 열기: 실패 - {type(e).__name__}: {e}")
        return

    # 3단계: Gemini에게 실제로 요청 (에러를 그대로 노출해서 원인 파악)
    prompt = (
        "이 이미지에 있는 모든 텍스트를 빠짐없이 추출해줘. "
        "설명 없이 텍스트만 출력해줘."
    )

    try:
        response = ocr_model.generate_content([prompt, image])

        # response.text를 바로 읽기 전에, 응답 자체의 상세 정보를 먼저 확인
        print(f"OCR 요청: API 호출 자체는 성공")

        # prompt_feedback: 요청이 안전 정책 등으로 차단됐는지 여기 나옴
        if hasattr(response, "prompt_feedback"):
            print(f"  prompt_feedback: {response.prompt_feedback}")

        # candidates: 실제 생성 결과 후보들. finish_reason이 원인을 알려줌
        if hasattr(response, "candidates") and response.candidates:
            for c in response.candidates:
                print(f"  finish_reason: {c.finish_reason}")
                if hasattr(c, "safety_ratings"):
                    print(f"  safety_ratings: {c.safety_ratings}")
        else:
            print(f"  candidates가 비어있음 (응답 자체가 생성되지 않음)")

        # 이제 실제 텍스트 읽기 시도
        try:
            print(f"결과 미리보기: {response.text[:200]}")
        except Exception as text_error:
            print(f"  [!] response.text 읽기 실패: {type(text_error).__name__}: {text_error}")

    except Exception as e:
        print(f"OCR 요청: 실패 (API 호출 자체가 실패)")
        print(f"  에러 타입: {type(e).__name__}")
        print(f"  에러 내용 전체: {str(e)}")


def main():
    df = pd.read_csv(RESULT_CSV)
    target = df[df["title"].astype(str).str.contains(TARGET_TITLE_KEYWORD, na=False)]

    if len(target) == 0:
        print(f"'{TARGET_TITLE_KEYWORD}' 가 포함된 공지를 못 찾았어요.")
        return

    for _, row in target.iterrows():
        print("=" * 60)
        print(f"공지 제목: {row['title']}")
        print(f"URL: {row['url']}")

        content_area = get_content_area(row["url"])
        image_urls = extract_image_urls(content_area)
        print(f"이미지 개수: {len(image_urls)}")

        for i, img_url in enumerate(image_urls, 1):
            diagnose_image(img_url, i)


if __name__ == "__main__":
    main()