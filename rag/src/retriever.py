from __future__ import annotations

from typing import Protocol

import numpy as np

if __package__:
    from .db import ChunkRepository
    from .preprocess import DEFAULT_PREPROCESSOR, QueryPreprocessor
else:
    from db import ChunkRepository
    from preprocess import DEFAULT_PREPROCESSOR, QueryPreprocessor


class EmbeddingModel(Protocol):
    def encode(self, text: str, normalize_embeddings: bool = True): ...


def _merge_rpc_rows(
    semantic_rows: list[dict],
    keyword_rows: list[dict],
    semantic_weight: float,
    keyword_weight: float,
) -> list[dict]:
    chunks: dict[object, dict] = {}

    for row in semantic_rows:
        chunk_id = row["chunk_id"]
        chunks[chunk_id] = {
            **row,
            "semantic_score": float(row["semantic_score"]),
            "keyword_score": 0.0,
            "matched_keywords": [],
        }

    for row in keyword_rows:
        chunk_id = row["chunk_id"]
        chunk = chunks.setdefault(
            chunk_id,
            {
                **row,
                "semantic_score": 0.0,
                "keyword_score": 0.0,
                "matched_keywords": [],
            },
        )
        chunk["keyword_score"] = max(
            chunk["keyword_score"],
            float(row["keyword_score"]),
        )

        for keyword in row.get("matched_keywords", []):
            if keyword not in chunk["matched_keywords"]:
                chunk["matched_keywords"].append(keyword)

    for chunk in chunks.values():
        chunk["hybrid_score"] = (
            chunk["semantic_score"] * semantic_weight
            + chunk["keyword_score"] * keyword_weight
        )

    return sorted(
        chunks.values(),
        key=lambda chunk: chunk["hybrid_score"],
        reverse=True,
    )


def _group_chunks_by_notice(
    chunks: list[dict],
    top_k: int,
) -> list[dict]:
    grouped: dict[object, dict] = {}

    for chunk in chunks:
        notice_id = chunk["notice_id"]

        if notice_id not in grouped:
            grouped[notice_id] = {
                "score": chunk["hybrid_score"],
                "hybrid_score": chunk["hybrid_score"],
                "semantic_score": chunk["semantic_score"],
                "keyword_score": chunk["keyword_score"],
                "matched_keywords": list(chunk["matched_keywords"]),
                "notice": {
                    "id": notice_id,
                    "title": chunk["title"],
                    "category": chunk["category"],
                    "published_at": chunk["published_at"],
                    "deadline": chunk.get("deadline"),
                    "url": chunk["url"],
                    "content": "",
                },
                "chunks": [],
            }

        result = grouped[notice_id]
        result["hybrid_score"] = max(
            result["hybrid_score"],
            chunk["hybrid_score"],
        )
        result["score"] = result["hybrid_score"]
        result["semantic_score"] = max(
            result["semantic_score"],
            chunk["semantic_score"],
        )
        result["keyword_score"] = max(
            result["keyword_score"],
            chunk["keyword_score"],
        )

        for keyword in chunk["matched_keywords"]:
            if keyword not in result["matched_keywords"]:
                result["matched_keywords"].append(keyword)

        result["chunks"].append(chunk)

    results = sorted(
        grouped.values(),
        key=lambda result: result["hybrid_score"],
        reverse=True,
    )[:top_k]

    for result in results:
        ordered_chunks = sorted(
            result["chunks"],
            key=lambda chunk: chunk["chunk_index"],
        )
        content_parts = []

        for chunk in ordered_chunks:
            content_text = str(chunk["content_text"]).strip()
            if content_text and content_text not in content_parts:
                content_parts.append(content_text)

        result["notice"]["content"] = "\n\n".join(content_parts)

    return results


def search_notice_chunks(
    model: EmbeddingModel,
    question: str,
    repository: ChunkRepository,
    top_k: int = 5,
    semantic_weight: float = 0.75,
    keyword_weight: float = 0.25,
    category_filter: str | None = None,
    deadline_from: str | None = None,
    exclude_notice_ids: tuple | list | set | None = None,
    preprocessor: QueryPreprocessor = DEFAULT_PREPROCESSOR,
) -> list[dict]:
    """Supabase의 벡터/키워드 RPC 결과를 공지 단위로 병합합니다."""
    query_embedding = np.asarray(
        model.encode(
            f"query: {question}",
            normalize_embeddings=True,
        ),
        dtype=np.float32,
    )
    keywords = preprocessor.extract_keywords(question)
    match_count = max(top_k * 4, top_k)

    semantic_rows = repository.match_notice_chunks(
        query_embedding=query_embedding.tolist(),
        match_count=match_count,
        category_filter=category_filter,
        deadline_from=deadline_from,
        exclude_notice_ids=exclude_notice_ids,
    )
    keyword_rows = []

    if keywords:
        keyword_rows = repository.search_notice_chunks_keyword(
            search_keywords=keywords,
            match_count=match_count,
            category_filter=category_filter,
            deadline_from=deadline_from,
            exclude_notice_ids=exclude_notice_ids,
        )

    chunks = _merge_rpc_rows(
        semantic_rows=semantic_rows,
        keyword_rows=keyword_rows,
        semantic_weight=semantic_weight,
        keyword_weight=keyword_weight,
    )

    return _group_chunks_by_notice(chunks, top_k=top_k)
