"""
공지 하나를 받아 청크로 나누고 임베딩해서 notice_chunks에 저장합니다.
청크 분할 로직은 이후 RAG 팀 쪽에서 개선될 수 있으므로, 이 파일만 교체하면
pipeline.py 쪽 코드는 그대로 유지되도록 분리했습니다.
"""

import hashlib
import json
import re
from datetime import datetime, timezone

import numpy as np

EMBEDDING_MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384
MIN_CHUNK_CHARS = 500
MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 100
TOKEN_OVERLAP = 48

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|\n+")
INLINE_WHITESPACE = re.compile(r"[ \t\f\v]+")


def normalize_notice_content(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [INLINE_WHITESPACE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def split_notice_content(content, min_chars=MIN_CHUNK_CHARS, max_chars=MAX_CHUNK_CHARS, overlap_chars=OVERLAP_CHARS):
    text = normalize_notice_content(content)
    if not text:
        return []

    chunks = []
    start = 0
    while start < len(text):
        max_end = min(start + max_chars, len(text))
        end = max_end

        if max_end < len(text):
            min_end = min(start + min_chars, max_end)
            boundaries = [
                m.end() for m in SENTENCE_BOUNDARY.finditer(text, start, max_end + 1)
                if m.end() >= min_end
            ]
            if boundaries:
                end = boundaries[-1]

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        start = max(end - overlap_chars, start + 1)

    return chunks


def build_chunk_text(notice: dict, content_text: str) -> str:
    category = notice.get("category")
    category_text = ", ".join(category) if isinstance(category, list) else (category or "")
    return (
        f"제목: {notice.get('title', '')}\n"
        f"카테고리: {category_text}\n"
        f"게시일: {notice.get('published_at', '')}\n"
        f"내용: {content_text}"
    )


def calculate_notice_hash(notice: dict) -> str:
    payload = json.dumps(
        {
            "title": normalize_notice_content(notice.get("title")),
            "category": normalize_notice_content(str(notice.get("category"))),
            "published_at": str(notice.get("published_at") or ""),
            "content": normalize_notice_content(notice.get("content")),
        },
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_chunk_drafts(notice: dict, tokenizer, max_sequence_tokens: int = 512) -> list[dict]:
    content_chunks = split_notice_content(notice.get("content")) or ["(본문 없음)"]
    content_hash = calculate_notice_hash(notice)

    metadata_prefix = build_chunk_text(notice, "")
    prefix_tokens = len(tokenizer.encode(f"passage: {metadata_prefix}", add_special_tokens=True))
    content_token_budget = max(64, max_sequence_tokens - prefix_tokens - 8)

    drafts = []
    for chunk_index, content_text in enumerate(content_chunks):
        # 너무 긴 청크는 자르기 (토큰 예산 기준 대략적 char 환산)
        if len(content_text) > content_token_budget * 3:
            content_text = content_text[: content_token_budget * 3]

        chunk_text = build_chunk_text(notice, content_text)
        token_count = len(tokenizer.encode(f"passage: {chunk_text}", add_special_tokens=True))

        drafts.append({
            "notice_id": notice["id"],
            "chunk_index": chunk_index,
            "content_text": content_text,
            "chunk_text": chunk_text,
            "token_count": token_count,
            "content_hash": content_hash,
        })

    return drafts


def generate_chunk_rows(notice: dict, model) -> list[dict]:
    tokenizer = model.tokenizer
    max_sequence_tokens = int(getattr(model, "max_seq_length", 512) or 512)
    drafts = create_chunk_drafts(notice, tokenizer, max_sequence_tokens)

    embedding_inputs = [f"passage: {d['chunk_text']}" for d in drafts]
    embeddings = np.asarray(
        model.encode(embedding_inputs, batch_size=16, normalize_embeddings=True),
        dtype=np.float32,
    )

    embedded_at = datetime.now(timezone.utc).isoformat()
    for draft, embedding in zip(drafts, embeddings, strict=True):
        draft["embedding"] = [round(float(v), 8) for v in embedding]
        draft["embedded_at"] = embedded_at

    return drafts


def save_notice_chunks(notice: dict, model, supabase_service_client) -> None:
    """
    공지 하나의 청크를 생성해 notice_chunks에 저장합니다.
    supabase_service_client는 반드시 service_role 키로 만든 클라이언트여야 합니다.
    """
    rows = generate_chunk_rows(notice, model)

    supabase_service_client.table("notice_chunks").upsert(
        rows, on_conflict="notice_id,chunk_index"
    ).execute()

    # 혹시 이전보다 청크 수가 줄어든 경우를 대비해 남는 청크 삭제
    supabase_service_client.table("notice_chunks").delete().eq(
        "notice_id", notice["id"]
    ).gte("chunk_index", len(rows)).execute()