from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

import numpy as np
import requests
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer

if __package__:
    from .db import ROOT_DIR, get_notice_repository
else:
    from db import ROOT_DIR, get_notice_repository


MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384
MIN_CHUNK_CHARS = 500
MAX_CHUNK_CHARS = 800
OVERLAP_CHARS = 100
TOKEN_OVERLAP = 48
DEFAULT_SQL_PATH = ROOT_DIR / "supabase" / "generated" / "notice_chunks_data.sql"

SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?。！？])\s+|\n+")
INLINE_WHITESPACE = re.compile(r"[ \t\f\v]+")


class ChunkGenerationError(RuntimeError):
    """청크 생성 또는 적재를 완료하지 못했을 때 발생합니다."""


class Tokenizer(Protocol):
    def encode(self, text: str, add_special_tokens: bool = True): ...

    def __call__(self, text: str, **kwargs): ...


def normalize_notice_content(value: object) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [INLINE_WHITESPACE.sub(" ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line).strip()


def _split_long_unit(
    unit: str,
    max_chars: int,
    overlap_chars: int,
) -> list[str]:
    if len(unit) <= max_chars:
        return [unit]

    step = max(max_chars - overlap_chars, 1)
    parts = []
    start = 0

    while start < len(unit):
        end = min(start + max_chars, len(unit))
        parts.append(unit[start:end].strip())

        if end == len(unit):
            break

        start += step

    return [part for part in parts if part]


def split_notice_content(
    content: object,
    min_chars: int = MIN_CHUNK_CHARS,
    max_chars: int = MAX_CHUNK_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[str]:
    """본문을 문장 경계 중심의 겹치는 청크로 나눕니다."""
    if min_chars <= 0 or max_chars < min_chars:
        raise ValueError("청크 글자 수 범위가 올바르지 않습니다.")

    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("청크 중첩 길이는 0 이상, 최대 길이 미만이어야 합니다.")

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
                match.end()
                for match in SENTENCE_BOUNDARY.finditer(text, start, max_end + 1)
                if match.end() >= min_end
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


def calculate_notice_hash(notice: dict) -> str:
    canonical_notice = {
        "title": normalize_notice_content(notice.get("title")),
        "category": normalize_notice_content(notice.get("category")),
        "published_at": str(notice.get("published_at") or ""),
        "content": normalize_notice_content(notice.get("content")),
    }
    payload = json.dumps(
        canonical_notice,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def select_notices_requiring_embedding(
    notices: list[dict],
    existing_hashes: dict[int, str | None],
) -> list[dict]:
    selected = []

    for notice in notices:
        notice_id = notice.get("id")

        if not isinstance(notice_id, int):
            raise ChunkGenerationError(
                f"공지 ID가 bigint 형태가 아닙니다: {notice_id}"
            )

        if existing_hashes.get(notice_id) != calculate_notice_hash(notice):
            selected.append(notice)

    return selected


def build_chunk_text(notice: dict, content_text: str) -> str:
    return (
        f"제목: {normalize_notice_content(notice.get('title'))}\n"
        f"카테고리: {normalize_notice_content(notice.get('category'))}\n"
        f"게시일: {notice.get('published_at') or ''}\n"
        f"내용: {content_text}"
    )


def _split_by_token_offsets(
    text: str,
    tokenizer: Tokenizer,
    max_tokens: int,
    overlap_tokens: int,
) -> list[str]:
    try:
        encoded = tokenizer(
            text,
            add_special_tokens=False,
            return_offsets_mapping=True,
        )
        token_ids = encoded["input_ids"]
        offsets = encoded["offset_mapping"]
    except (KeyError, TypeError, ValueError, NotImplementedError):
        token_ids = tokenizer.encode(text, add_special_tokens=False)
        offsets = None

    if len(token_ids) <= max_tokens:
        return [text]

    if not offsets:
        estimated_chars = max(1, int(len(text) * max_tokens / len(token_ids)))
        estimated_overlap = max(
            1,
            int(estimated_chars * overlap_tokens / max_tokens),
        )
        return _split_long_unit(text, estimated_chars, estimated_overlap)

    parts = []
    start_token = 0
    step = max(max_tokens - overlap_tokens, 1)

    while start_token < len(offsets):
        end_token = min(start_token + max_tokens, len(offsets))
        window_offsets = [
            offset for offset in offsets[start_token:end_token] if offset[1] > offset[0]
        ]

        if window_offsets:
            char_start = window_offsets[0][0]
            char_end = window_offsets[-1][1]
            part = text[char_start:char_end].strip()

            if part:
                parts.append(part)

        if end_token == len(offsets):
            break

        start_token += step

    return parts


def create_chunk_drafts(
    notices: list[dict],
    tokenizer: Tokenizer,
    max_sequence_tokens: int = 512,
) -> list[dict]:
    drafts = []

    for notice in notices:
        notice_id = notice.get("id")

        if not isinstance(notice_id, int):
            raise ChunkGenerationError(f"공지 ID가 bigint 형태가 아닙니다: {notice_id}")

        normalized_content = normalize_notice_content(notice.get("content"))
        content_chunks = split_notice_content(normalized_content)

        if not content_chunks:
            content_chunks = ["(본문 없음)"]

        metadata_prefix = build_chunk_text(notice, "")
        prefix_token_count = len(
            tokenizer.encode(
                f"passage: {metadata_prefix}",
                add_special_tokens=True,
            )
        )
        content_token_budget = max(64, max_sequence_tokens - prefix_token_count - 8)
        token_limited_chunks = []

        for content_chunk in content_chunks:
            token_limited_chunks.extend(
                _split_by_token_offsets(
                    text=content_chunk,
                    tokenizer=tokenizer,
                    max_tokens=content_token_budget,
                    overlap_tokens=min(TOKEN_OVERLAP, content_token_budget // 4),
                )
            )

        content_hash = calculate_notice_hash(notice)

        for chunk_index, content_text in enumerate(token_limited_chunks):
            chunk_text = build_chunk_text(notice, content_text)
            token_count = len(
                tokenizer.encode(
                    f"passage: {chunk_text}",
                    add_special_tokens=True,
                )
            )

            if token_count > max_sequence_tokens:
                raise ChunkGenerationError(
                    f"공지 {notice_id}의 {chunk_index}번 청크가 "
                    f"모델 한도를 초과했습니다: {token_count}"
                )

            drafts.append({
                "notice_id": notice_id,
                "chunk_index": chunk_index,
                "content_text": content_text,
                "chunk_text": chunk_text,
                "token_count": token_count,
                "content_hash": content_hash,
            })

    return drafts


def generate_chunk_rows(
    notices: list[dict],
    model: SentenceTransformer,
    batch_size: int = 16,
) -> list[dict]:
    tokenizer = model.tokenizer
    max_sequence_tokens = int(getattr(model, "max_seq_length", 512) or 512)
    drafts = create_chunk_drafts(
        notices=notices,
        tokenizer=tokenizer,
        max_sequence_tokens=max_sequence_tokens,
    )

    embedding_inputs = [f"passage: {draft['chunk_text']}" for draft in drafts]
    embeddings = np.asarray(
        model.encode(
            embedding_inputs,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
        ),
        dtype=np.float32,
    )

    if embeddings.shape != (len(drafts), EMBEDDING_DIMENSION):
        raise ChunkGenerationError(
            "임베딩 배열 크기가 올바르지 않습니다: "
            f"{embeddings.shape}"
        )

    if not np.isfinite(embeddings).all():
        raise ChunkGenerationError("임베딩에 유효하지 않은 숫자가 포함되어 있습니다.")

    norms = np.linalg.norm(embeddings, axis=1)

    if not np.allclose(norms, 1.0, atol=1e-3):
        raise ChunkGenerationError("정규화되지 않은 임베딩이 생성되었습니다.")

    embedded_at = datetime.now(timezone.utc).isoformat()

    for draft, embedding in zip(drafts, embeddings, strict=True):
        draft["embedding"] = [round(float(value), 8) for value in embedding]
        draft["embedded_at"] = embedded_at

    return drafts


def get_chunk_manifest(rows: list[dict]) -> list[dict]:
    counts: dict[int, int] = defaultdict(int)

    for row in rows:
        counts[int(row["notice_id"])] = max(
            counts[int(row["notice_id"])],
            int(row["chunk_index"]) + 1,
        )

    return [
        {"notice_id": notice_id, "chunk_count": chunk_count}
        for notice_id, chunk_count in sorted(counts.items())
    ]


class SupabaseChunkWriter:
    def __init__(
        self,
        url: str,
        secret_key: str,
        session: requests.Session | None = None,
    ) -> None:
        if not url or not secret_key:
            raise ChunkGenerationError(
                "SUPABASE_URL과 SUPABASE_SECRET_KEY 또는 "
                "SUPABASE_SERVICE_ROLE_KEY가 필요합니다."
            )

        self.url = url.rstrip("/")
        self.session = session or requests.Session()
        self.headers = {
            "apikey": secret_key,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=minimal",
        }

    def fetch_chunk_hashes(
        self,
        page_size: int = 1000,
    ) -> dict[int, str | None]:
        if page_size <= 0:
            raise ValueError("해시 조회 페이지 크기는 1 이상이어야 합니다.")

        indexes_by_notice: dict[int, set[int]] = defaultdict(set)
        hashes_by_notice: dict[int, set[str]] = defaultdict(set)
        offset = 0

        while True:
            try:
                response = self.session.get(
                    f"{self.url}/rest/v1/notice_chunks",
                    headers={
                        "apikey": self.headers["apikey"],
                        "Accept": "application/json",
                    },
                    params={
                        "select": "notice_id,chunk_index,content_hash",
                        "order": "notice_id.asc,chunk_index.asc",
                        "limit": page_size,
                        "offset": offset,
                    },
                    timeout=30,
                )
                response.raise_for_status()
                page = response.json()
            except (requests.RequestException, ValueError) as error:
                raise ChunkGenerationError(
                    "기존 notice_chunks 해시 조회에 실패했습니다."
                ) from error

            if not isinstance(page, list):
                raise ChunkGenerationError(
                    "notice_chunks 해시 응답이 배열 형태가 아닙니다."
                )

            for row in page:
                if not isinstance(row, dict):
                    raise ChunkGenerationError(
                        "notice_chunks 해시 응답에 잘못된 행이 있습니다."
                    )

                notice_id = row.get("notice_id")
                chunk_index = row.get("chunk_index")
                content_hash = row.get("content_hash")

                if (
                    not isinstance(notice_id, int)
                    or not isinstance(chunk_index, int)
                    or not isinstance(content_hash, str)
                ):
                    raise ChunkGenerationError(
                        "notice_chunks 해시 응답의 타입이 올바르지 않습니다."
                    )

                indexes_by_notice[notice_id].add(chunk_index)
                hashes_by_notice[notice_id].add(content_hash)

            if len(page) < page_size:
                break

            offset += page_size

        existing_hashes: dict[int, str | None] = {}

        for notice_id, notice_indexes in indexes_by_notice.items():
            indexes = sorted(notice_indexes)
            hashes = hashes_by_notice[notice_id]
            indexes_are_contiguous = indexes == list(range(len(indexes)))

            if indexes_are_contiguous and len(hashes) == 1:
                existing_hashes[notice_id] = next(iter(hashes))
            else:
                existing_hashes[notice_id] = None

        return existing_hashes

    def replace_chunks(self, rows: list[dict], batch_size: int = 50) -> None:
        for start in range(0, len(rows), batch_size):
            response = self.session.post(
                f"{self.url}/rest/v1/notice_chunks",
                headers=self.headers,
                params={"on_conflict": "notice_id,chunk_index"},
                json=rows[start:start + batch_size],
                timeout=60,
            )

            try:
                response.raise_for_status()
            except requests.RequestException as error:
                raise ChunkGenerationError(
                    f"청크 {start}~{start + batch_size} 적재에 실패했습니다: "
                    f"{response.text}"
                ) from error

        for item in get_chunk_manifest(rows):
            response = self.session.delete(
                f"{self.url}/rest/v1/notice_chunks",
                headers=self.headers,
                params={
                    "notice_id": f"eq.{item['notice_id']}",
                    "chunk_index": f"gte.{item['chunk_count']}",
                },
                timeout=30,
            )

            try:
                response.raise_for_status()
            except requests.RequestException as error:
                raise ChunkGenerationError(
                    f"공지 {item['notice_id']}의 오래된 청크 삭제에 실패했습니다: "
                    f"{response.text}"
                ) from error


def upload_with_temporary_rpc(
    rows: list[dict],
    url: str,
    publishable_key: str,
    ingest_token: str,
    batch_size: int = 50,
    session: requests.Session | None = None,
) -> None:
    if not url or not publishable_key or not ingest_token:
        raise ChunkGenerationError("임시 적재 RPC 설정이 완전하지 않습니다.")

    http = session or requests.Session()
    endpoint = f"{url.rstrip('/')}/rest/v1/rpc/ingest_notice_chunks_temp"
    headers = {
        "apikey": publishable_key,
        "Content-Type": "application/json",
    }

    for start in range(0, len(rows), batch_size):
        response = http.post(
            endpoint,
            headers=headers,
            json={
                "ingest_token": ingest_token,
                "chunk_rows": rows[start:start + batch_size],
                "chunk_manifest": None,
            },
            timeout=60,
        )

        try:
            response.raise_for_status()
        except requests.RequestException as error:
            raise ChunkGenerationError(
                f"임시 RPC 청크 {start}~{start + batch_size} 적재에 실패했습니다: "
                f"{response.text}"
            ) from error

    response = http.post(
        endpoint,
        headers=headers,
        json={
            "ingest_token": ingest_token,
            "chunk_rows": [],
            "chunk_manifest": get_chunk_manifest(rows),
        },
        timeout=60,
    )

    try:
        response.raise_for_status()
    except requests.RequestException as error:
        raise ChunkGenerationError(
            f"임시 RPC 청크 정리에 실패했습니다: {response.text}"
        ) from error


def write_chunk_sql(rows: list[dict], output_path: Path) -> None:
    rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    manifest_json = json.dumps(
        get_chunk_manifest(rows),
        ensure_ascii=False,
        separators=(",", ":"),
    )

    if "$notice_chunks$" in rows_json or "$notice_chunks$" in manifest_json:
        raise ChunkGenerationError("SQL dollar quote와 충돌하는 본문이 있습니다.")

    sql = f"""begin;

with rows as (
  select *
  from jsonb_to_recordset($notice_chunks${rows_json}$notice_chunks$::jsonb)
    as row(
      notice_id bigint,
      chunk_index integer,
      content_text text,
      chunk_text text,
      token_count integer,
      content_hash text,
      embedding jsonb,
      embedded_at timestamptz
    )
)
insert into public.notice_chunks (
  notice_id,
  chunk_index,
  content_text,
  chunk_text,
  token_count,
  content_hash,
  embedding,
  embedded_at
)
select
  notice_id,
  chunk_index,
  content_text,
  chunk_text,
  token_count,
  content_hash,
  embedding::text::public.vector,
  embedded_at
from rows
on conflict (notice_id, chunk_index) do update set
  content_text = excluded.content_text,
  chunk_text = excluded.chunk_text,
  token_count = excluded.token_count,
  content_hash = excluded.content_hash,
  embedding = excluded.embedding,
  embedded_at = excluded.embedded_at;

with manifest as (
  select *
  from jsonb_to_recordset($notice_chunks${manifest_json}$notice_chunks$::jsonb)
    as item(notice_id bigint, chunk_count integer)
)
delete from public.notice_chunks as chunks
using manifest
where chunks.notice_id = manifest.notice_id
  and chunks.chunk_index >= manifest.chunk_count;

commit;
"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(sql, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Supabase notices를 RAG 청크와 E5 임베딩으로 변환합니다."
    )
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--upload-batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--force",
        action="store_true",
        help="기존 content_hash와 관계없이 모든 공지를 다시 생성합니다.",
    )
    parser.add_argument("--output-sql", type=Path, default=DEFAULT_SQL_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv(ROOT_DIR / ".env")

    repository = get_notice_repository("supabase")
    notices = repository.fetch_notices()

    if args.limit is not None:
        notices = notices[:max(args.limit, 0)]

    if not notices:
        raise ChunkGenerationError("변환할 공지가 없습니다.")

    print(f"Supabase에서 공지 {len(notices)}개를 불러왔습니다.")

    supabase_url = os.getenv("SUPABASE_URL", "")
    ingest_token = os.getenv("NOTICE_CHUNK_INGEST_TOKEN", "")
    secret_key = (
        os.getenv("SUPABASE_SECRET_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    )
    writer = None
    notices_to_embed = notices

    if args.apply and not ingest_token:
        writer = SupabaseChunkWriter(
            url=supabase_url,
            secret_key=secret_key,
        )

        if not args.force:
            existing_hashes = writer.fetch_chunk_hashes()
            notices_to_embed = select_notices_requiring_embedding(
                notices,
                existing_hashes,
            )
            print(
                "content_hash 비교 결과: "
                f"변경 또는 신규 {len(notices_to_embed)}개, "
                f"변경 없음 {len(notices) - len(notices_to_embed)}개"
            )

    if not notices_to_embed:
        print("변경된 공지가 없어 청크 생성과 적재를 생략합니다.")
        return

    print(f"임베딩 모델을 불러옵니다: {args.model}")
    model = SentenceTransformer(args.model)
    rows = generate_chunk_rows(
        notices=notices_to_embed,
        model=model,
        batch_size=args.batch_size,
    )

    manifest = get_chunk_manifest(rows)
    print(
        f"공지 {len(manifest)}개에서 청크 {len(rows)}개를 생성했습니다."
    )

    if not args.apply:
        write_chunk_sql(rows, args.output_sql)
        print(f"SQL 파일을 생성했습니다: {args.output_sql}")
        return

    if ingest_token:
        upload_with_temporary_rpc(
            rows=rows,
            url=supabase_url,
            publishable_key=os.getenv("SUPABASE_KEY", ""),
            ingest_token=ingest_token,
            batch_size=args.upload_batch_size,
        )
    else:
        if writer is None:
            raise ChunkGenerationError("Supabase 청크 writer가 준비되지 않았습니다.")

        writer.replace_chunks(rows, batch_size=args.upload_batch_size)

    print("Supabase notice_chunks 적재를 완료했습니다.")


if __name__ == "__main__":
    main()
