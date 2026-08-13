"""Rebuild every notice chunk with Gemini embeddings.

Run once before deploying a chatbot that creates Gemini query embeddings:
    python pipeline/reembed_notice_chunks.py
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
load_dotenv(ROOT_DIR / ".env")

from chunk_and_embed import save_notice_chunks  # noqa: E402
from rag.src.embedding import GeminiEmbeddingModel  # noqa: E402


def fetch_notices(client, page_size: int = 100) -> list[dict]:
    notices: list[dict] = []
    offset = 0

    while True:
        response = (
            client.table("notices")
            .select("id,title,url,category,content,published_at")
            .order("id")
            .range(offset, offset + page_size - 1)
            .execute()
        )
        page = response.data or []
        notices.extend(page)
        if len(page) < page_size:
            return notices
        offset += page_size


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-id", type=int, default=0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()

    try:
        from supabase import create_client
    except ImportError as error:
        raise SystemExit(
            "supabase 패키지가 없습니다. 먼저 `pip install -r requirements.txt`를 "
            "실행하세요."
        ) from error

    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not service_key:
        raise SystemExit(
            "SUPABASE_URL과 SUPABASE_SERVICE_ROLE_KEY가 필요합니다."
        )
    if not os.getenv("GEMINI_API_KEY"):
        raise SystemExit("GEMINI_API_KEY가 필요합니다.")

    client = create_client(supabase_url, service_key)
    notices = [
        notice
        for notice in fetch_notices(client)
        if int(notice["id"]) >= args.start_id
    ]
    if args.limit is not None:
        notices = notices[: args.limit]

    model = GeminiEmbeddingModel()
    total = len(notices)
    print(f"Gemini로 공지 {total}건을 재임베딩합니다.")

    for index, notice in enumerate(notices, start=1):
        try:
            save_notice_chunks(notice, model, client)
        except Exception as error:
            print(
                f"실패 {index}/{total}: id={notice['id']} error={error}",
                file=sys.stderr,
            )
            print(
                "해결 후 --start-id로 실패한 공지부터 다시 실행하세요.",
                file=sys.stderr,
            )
            raise SystemExit(1) from error
        print(f"완료 {index}/{total}: id={notice['id']} {notice.get('title', '')}")


if __name__ == "__main__":
    main()
