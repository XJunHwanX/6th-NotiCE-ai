"""
컴공 공지 알리미 - 자동 파이프라인 (최종본)
GitHub Actions로 주기적 실행 (예: 6시간마다)

흐름:
1. 컴공과 게시판 최신 목록 크롤링 (crawl_cse.py 로직)
2. Supabase notices에 이미 있는 source_notice_id는 건너뜀 (중복 방지)
3. 새 공지만 골라서:
   a. 본문 크롤링 + 표/이미지 OCR (crawl_content.py 로직)
   b. 분류 모델로 제목 기반 카테고리 예측 (threshold 0.6, 복수 카테고리 가능)
   c. notices 테이블에 insert (category는 배열)
4. 방금 추가된 공지의 카테고리를 구독한 사용자들에게 웹 푸시 발송
   (subscriptions.categories와 겹치는 구독자에게 발송)

실행: python pipeline/pipeline.py

필요 환경변수(.env 또는 GitHub Secrets):
    SUPABASE_URL, SUPABASE_KEY
    GEMINI_API_KEY            (본문 이미지 OCR용)
    VAPID_PRIVATE_KEY_PATH    (기본값 private_key.pem)
    VAPID_CLAIMS_EMAIL
    MODEL_DRIVE_FOLDER_ID     (구글드라이브 모델 폴더 ID, 로컬에 모델 없을 때 다운로드용)
"""

import os
import re
import time
import sys
from io import StringIO

import requests
from bs4 import BeautifulSoup
import pandas as pd
from dotenv import load_dotenv
from supabase import create_client
from pywebpush import webpush, WebPushException

from dotenv import load_dotenv


# pipeline.py가 있는 폴더 기준으로 .env 찾기
load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

# backend 폴더의 notice_classifier를 import할 수 있게 경로 추가
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "backend"))
from notice_classifier import load_classifier, predict_category  # noqa: E402


# ============================================
# 설정
# ============================================
HEADERS = {"User-Agent": "Mozilla/5.0"}
LIST_URL = "https://wwwce.hongik.ac.kr/wwwce/0401.do"
BASE_URL = "https://wwwce.hongik.ac.kr"
CHECK_LIMIT = 30  # 매 실행마다 최신 몇 개까지 확인할지

MODEL_DIR = os.path.join(os.path.dirname(__file__), "model_final_v5")
MODEL_DRIVE_FOLDER_ID = os.getenv("MODEL_DRIVE_FOLDER_ID", "")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
USE_OCR = bool(GEMINI_API_KEY)
MIN_IMAGE_SIZE = 200
OCR_MAX_RETRY = 2
OCR_DELAY = 3
PAGE_DELAY = 1

VAPID_PRIVATE_KEY_PATH = os.getenv("VAPID_PRIVATE_KEY_PATH", "private_key.pem")
VAPID_CLAIMS = {"sub": f"mailto:{os.getenv('VAPID_CLAIMS_EMAIL', 'admin@example.com')}"}

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise SystemExit("SUPABASE_URL / SUPABASE_KEY가 설정되지 않았습니다.")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

if USE_OCR:
    import google.generativeai as genai
    genai.configure(api_key=GEMINI_API_KEY)
    ocr_model = genai.GenerativeModel("gemini-flash-latest")


# ============================================
# 0. 모델 준비 (로컬에 없으면 구글드라이브에서 다운로드)
# ============================================
def ensure_model_downloaded():
    if os.path.exists(MODEL_DIR):
        return
    if not MODEL_DRIVE_FOLDER_ID:
        raise SystemExit(
            f"{MODEL_DIR}가 없고 MODEL_DRIVE_FOLDER_ID도 설정되지 않았습니다. "
            "모델을 로컬에 두거나 드라이브 폴더 ID를 설정하세요."
        )
    import gdown
    print("모델을 구글드라이브에서 다운로드 중...")
    gdown.download_folder(id=MODEL_DRIVE_FOLDER_ID, output=MODEL_DIR, quiet=False)


# ============================================
# 1. 최신 공지 목록 크롤링 (crawl_cse.py 로직)
# ============================================
def get_latest_notices(limit=CHECK_LIMIT):
    notices = []
    offset = 0

    while len(notices) < limit:
        params = {"mode": "list", "article.offset": offset, "articleLimit": 10}
        res = requests.get(LIST_URL, headers=HEADERS, params=params)
        soup = BeautifulSoup(res.text, "html.parser")

        rows = soup.find("table").find("tbody").find_all("tr")
        if not rows:
            break

        for row in rows:
            title_tag = row.find("span", class_="b-title")
            link_tag = row.find("div", class_="b-title-box").find("a")
            date_tag = row.find("span", class_="b-date")

            title = title_tag.get_text(strip=True)
            href = link_tag.get("href")
            url = LIST_URL + href
            date = date_tag.get_text(strip=True)
            article_no = int(re.search(r"articleNo=(\d+)", href).group(1))

            notices.append({
                "article_no": article_no,
                "title": title,
                "url": url,
                "published_at": date.replace(".", "-").rstrip("-"),
            })

            if len(notices) >= limit:
                break

        offset += 10
        time.sleep(0.3)

    return notices


# ============================================
# 2. 본문 크롤링 + OCR (crawl_content.py 로직)
# ============================================
def get_content_area(url):
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


def extract_text(content_area):
    if content_area is None:
        return ""
    text = content_area.get_text(separator="\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def extract_tables(content_area):
    if content_area is None:
        return ""
    tables = content_area.find_all("table")
    if not tables:
        return ""

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
    if not USE_OCR:
        return ""

    from PIL import Image
    from io import BytesIO

    try:
        img_response = requests.get(image_url, headers=HEADERS, timeout=15)
        img_response.raise_for_status()
        image = Image.open(BytesIO(img_response.content))
    except Exception as e:
        print(f"  [경고] 이미지 다운로드 실패: {type(e).__name__}")
        return ""

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

    for attempt in range(OCR_MAX_RETRY + 1):
        try:
            response = ocr_model.generate_content([prompt, image])
            return response.text.strip()
        except Exception as e:
            error_name = type(e).__name__
            if "ResourceExhausted" in error_name or "429" in str(e):
                wait = 30 * (attempt + 1)
                print(f"  [대기] Rate limit 감지, {wait}초 대기 후 재시도...")
                time.sleep(wait)
            else:
                print(f"  [경고] OCR 시도 {attempt + 1} 실패: {error_name}")
                time.sleep(3)

    print(f"  [실패] OCR 최종 실패: {image_url}")
    return ""


def extract_full_content(url):
    content_area = get_content_area(url)
    if content_area is None:
        return ""

    text = extract_text(content_area)

    table_text = extract_tables(content_area)
    if table_text:
        text += "\n\n[표 내용]\n" + table_text

    image_urls = extract_image_urls(content_area)
    if image_urls and USE_OCR:
        ocr_texts = []
        for img_url in image_urls:
            ocr_text = ocr_image(img_url)
            if ocr_text:
                ocr_texts.append(ocr_text)
            time.sleep(OCR_DELAY)
        if ocr_texts:
            text += "\n\n[이미지 OCR 내용]\n" + "\n".join(ocr_texts)

    return text.strip()


# ============================================
# 3. 이미 DB에 있는 article_no 확인
# ============================================
def get_existing_article_nos(article_nos):
    result = supabase.table("notices").select("source_notice_id").in_(
        "source_notice_id", [str(n) for n in article_nos]
    ).execute()
    return {int(row["source_notice_id"]) for row in result.data}


# ============================================
# 4. 구독자 조회 (categories 배열 중 하나라도 겹치면)
# ============================================
def get_subscribers_for_categories(categories):
    result = supabase.table("subscriptions").select("*").execute()
    matched = []
    for sub in result.data:
        sub_categories = sub.get("categories") or []
        if any(c in sub_categories for c in categories):
            matched.append(sub)
    return matched


# ============================================
# 5. 웹 푸시 발송
# ============================================
def send_push_notification(subscription, title, url):
    if not subscription.get("endpoint"):
        return False  # 아직 웹푸시 구독 정보가 없는 레코드는 건너뜀

    subscription_info = {
        "endpoint": subscription["endpoint"],
        "keys": {
            "p256dh": subscription["p256dh"],
            "auth": subscription["auth"],
        },
    }
    try:
        webpush(
            subscription_info=subscription_info,
            data=f'{{"title": "새 공지", "body": "{title}", "url": "{url}"}}',
            vapid_private_key=VAPID_PRIVATE_KEY_PATH,
            vapid_claims=VAPID_CLAIMS,
        )
        return True
    except WebPushException as e:
        print(f"  [푸시 실패] {e}")
        return False


# ============================================
# 메인 파이프라인
# ============================================
def main():
    print("=== 파이프라인 시작 ===")

    print("0. 모델 준비 확인 중...")
    ensure_model_downloaded()

    print("1. 최신 공지 목록 크롤링 중...")
    latest_notices = get_latest_notices()
    print(f"   {len(latest_notices)}개 확인")

    article_nos = [n["article_no"] for n in latest_notices]
    existing = get_existing_article_nos(article_nos)
    new_notices = [n for n in latest_notices if n["article_no"] not in existing]

    print(f"2. 새 공지 {len(new_notices)}개 발견 (기존 {len(existing)}개 제외)")

    if not new_notices:
        print("새 공지가 없습니다. 종료합니다.")
        return

    print("3. 분류 모델 로드 중...")
    classifier = load_classifier(MODEL_DIR)

    for notice in new_notices:
        print(f"\n[{notice['article_no']}] {notice['title'][:40]}")

        print("   본문 크롤링 중...")
        body_text = extract_full_content(notice["url"])

        categories = predict_category(classifier, notice["title"])
        print(f"   분류 결과: {categories}")

        supabase.table("notices").insert({
            "source_notice_id": notice["article_no"],
            "title": notice["title"],
            "url": notice["url"],
            "published_at": notice["published_at"],
            "category": categories,
            "content": body_text,
        }).execute()
        print("   DB 저장 완료")

        subscribers = get_subscribers_for_categories(categories)
        print(f"   구독자 {len(subscribers)}명에게 알림 발송 시도...")
        sent_count = 0
        for sub in subscribers:
            if send_push_notification(sub, notice["title"], notice["url"]):
                sent_count += 1
        print(f"   {sent_count}건 발송 완료")

        time.sleep(PAGE_DELAY)

    print("\n=== 파이프라인 종료 ===")


if __name__ == "__main__":
    main()