import unittest

import numpy as np

from rag.src.retriever import search_notice_chunks


class FakeModel:
    def encode(self, text, normalize_embeddings=True):
        return np.asarray([0.1, 0.2, 0.3], dtype=np.float32)


def chunk_row(chunk_id, notice_id, chunk_index, content, semantic_score):
    return {
        "chunk_id": chunk_id,
        "notice_id": notice_id,
        "chunk_index": chunk_index,
        "content_text": content,
        "semantic_score": semantic_score,
        "title": f"공지 {notice_id}",
        "category": "장학/근로",
        "published_at": "2026-05-22",
        "url": f"https://example.com/{notice_id}",
    }


class FakeChunkRepository:
    def __init__(self):
        self.semantic_calls = []
        self.keyword_calls = []

    def match_notice_chunks(self, **kwargs):
        self.semantic_calls.append(kwargs)
        return [
            chunk_row(100, 10, 0, "신청 기간 안내", 0.8),
            chunk_row(101, 10, 1, "제출 서류 안내", 0.7),
            chunk_row(200, 20, 0, "다른 공지", 0.75),
        ]

    def search_notice_chunks_keyword(self, **kwargs):
        self.keyword_calls.append(kwargs)
        row = chunk_row(100, 10, 0, "신청 기간 안내", 0.0)
        row.pop("semantic_score")
        row["keyword_score"] = 0.9
        row["matched_keywords"] = ["장학금", "신청"]
        return [row]


class ChunkRetrieverTests(unittest.TestCase):
    def test_merges_rpc_scores_and_groups_chunks_by_notice(self):
        repository = FakeChunkRepository()

        results = search_notice_chunks(
            model=FakeModel(),
            question="장학금 신청 서류 알려줘",
            repository=repository,
            top_k=2,
            exclude_notice_ids=[30],
        )

        self.assertEqual([result["notice"]["id"] for result in results], [10, 20])
        self.assertAlmostEqual(results[0]["hybrid_score"], 0.825)
        self.assertEqual(results[0]["matched_keywords"], ["장학금", "신청"])
        self.assertEqual(
            results[0]["notice"]["content"],
            "신청 기간 안내\n\n제출 서류 안내",
        )
        self.assertEqual(
            repository.semantic_calls[0]["exclude_notice_ids"],
            [30],
        )
        self.assertEqual(repository.semantic_calls[0]["match_count"], 8)
        self.assertEqual(repository.keyword_calls[0]["match_count"], 8)


if __name__ == "__main__":
    unittest.main()
