import os
import sys
import time
from datetime import datetime, timedelta

from dotenv import load_dotenv
from supabase import create_client
import google.generativeai as genai

sys.path.append(os.path.dirname(__file__))
from extract_deadline import extract_deadline

BACKFILL_DAYS = 90
REQUEST_DELAY = 15  # Gemini 무료 티어 분당 5회 제한 대응

load_dotenv(os.path.join(os.path.dirname(__file__), '.env'))

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    raise SystemExit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 설정되지 않았습니다.")

if not GEMINI_API_KEY:
    raise SystemExit("GEMINI_API_KEY가 설정되지 않았습니다.")

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

genai.configure(api_key=GEMINI_API_KEY)
ocr_model = genai.GenerativeModel("gemini-flash-latest")


def main():
    cutoff = (datetime.now() - timedelta(days=BACKFILL_DAYS)).strftime("%Y-%m-%d")

    print(f"=== 마감일 백필 시작 (최근 {BACKFILL_DAYS}일 이내, {cutoff} 이후 게시된 공지 대상) ===")

    result = (
        supabase.table("notices")
        .select("id, title, content, published_at")
        .is_("deadline", "null")
        .gte("published_at", cutoff)
        .execute()
    )

    notices = result.data
    print(f"대상 공지 {len(notices)}개\n")

    if not notices:
        print("채울 공지가 없습니다. 종료합니다.")
        return

    filled_count = 0
    empty_count = 0

    for index, notice in enumerate(notices):
        title_preview = notice["title"][:30]
        print(f"[{notice['id']}] {title_preview}")

        deadline = extract_deadline(
            title=notice["title"],
            content=notice.get("content") or "",
            published_at=notice["published_at"],
            ocr_model=ocr_model,
        )

        if deadline:
            supabase.table("notices").update({"deadline": deadline}).eq("id", notice["id"]).execute()
            print(f"   -> {deadline}")
            filled_count += 1
        else:
            print("   -> 없음")
            empty_count += 1

        # 마지막 공지가 아니면 대기 (분당 요청 한도 대응)
        if index < len(notices) - 1:
            time.sleep(REQUEST_DELAY)

    print(f"\n=== 백필 완료: {filled_count}개 채움, {empty_count}개 마감일 없음 ===")


if __name__ == "__main__":
    main()