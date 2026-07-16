import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

from rag.src import chunk_notices
from rag.src.chunk_notices import (
    EMBEDDING_DIMENSION,
    SupabaseChunkWriter,
    calculate_notice_hash,
    create_chunk_drafts,
    generate_chunk_rows,
    get_chunk_manifest,
    normalize_notice_content,
    select_notices_requiring_embedding,
    split_notice_content,
    write_chunk_sql,
)


class FakeTokenizer:
    def encode(self, text, add_special_tokens=True):
        tokens = list(text)
        return ([0] if add_special_tokens else []) + tokens

    def __call__(self, text, **kwargs):
        return {
            "input_ids": list(text),
            "offset_mapping": [(index, index + 1) for index in range(len(text))],
        }


class FakeModel:
    tokenizer = FakeTokenizer()
    max_seq_length = 512

    def encode(self, texts, **kwargs):
        embeddings = np.zeros((len(texts), EMBEDDING_DIMENSION), dtype=np.float32)
        embeddings[:, 0] = 1.0
        return embeddings


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self.rows


class FakeChunkStateSession:
    def __init__(self, pages):
        self.pages = pages
        self.requests = []

    def get(self, url, headers, params, timeout):
        self.requests.append({
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
        })
        return FakeResponse(self.pages[params["offset"]])


def make_notice(content="공지 본문입니다.", notice_id=9):
    return {
        "id": notice_id,
        "source_notice_id": f"notice-{notice_id}",
        "title": "수강 신청 안내",
        "url": f"https://example.com/{notice_id}",
        "category": "학사",
        "content": content,
        "published_at": "2026-07-01",
    }


class ChunkNoticeTest(unittest.TestCase):
    def test_normalize_notice_content_preserves_meaningful_lines(self):
        self.assertEqual(
            normalize_notice_content("  첫째  항목\r\n\r\n 둘째\t항목 "),
            "첫째 항목\n둘째 항목",
        )

    def test_split_notice_content_limits_size_and_overlaps_long_text(self):
        content = "가" * 1700
        chunks = split_notice_content(content)

        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(len(chunk) <= 800 for chunk in chunks))
        self.assertEqual(chunks[0][-100:], chunks[1][:100])

    def test_notice_hash_is_stable_and_changes_with_content(self):
        notice = make_notice()
        first_hash = calculate_notice_hash(notice)
        second_hash = calculate_notice_hash({**notice})
        changed_hash = calculate_notice_hash({**notice, "content": "수정된 본문"})

        self.assertEqual(first_hash, second_hash)
        self.assertNotEqual(first_hash, changed_hash)
        self.assertEqual(len(first_hash), 64)

    def test_selects_only_new_changed_or_unhealthy_notices(self):
        unchanged = make_notice(notice_id=9)
        changed = make_notice(content="수정된 본문", notice_id=10)
        unhealthy = make_notice(notice_id=11)
        new = make_notice(notice_id=12)
        existing_hashes = {
            9: calculate_notice_hash(unchanged),
            10: "0" * 64,
            11: None,
        }

        selected = select_notices_requiring_embedding(
            [unchanged, changed, unhealthy, new],
            existing_hashes,
        )

        self.assertEqual(
            [notice["id"] for notice in selected],
            [10, 11, 12],
        )

    def test_fetch_chunk_hashes_marks_inconsistent_chunks_unhealthy(self):
        session = FakeChunkStateSession({
            0: [
                {
                    "notice_id": 9,
                    "chunk_index": 0,
                    "content_hash": "a" * 64,
                },
                {
                    "notice_id": 9,
                    "chunk_index": 1,
                    "content_hash": "a" * 64,
                },
            ],
            2: [
                {
                    "notice_id": 10,
                    "chunk_index": 0,
                    "content_hash": "b" * 64,
                },
                {
                    "notice_id": 10,
                    "chunk_index": 2,
                    "content_hash": "b" * 64,
                },
            ],
            4: [],
        })
        writer = SupabaseChunkWriter(
            url="https://example.supabase.co",
            secret_key="test-secret",
            session=session,
        )

        hashes = writer.fetch_chunk_hashes(page_size=2)

        self.assertEqual(hashes, {9: "a" * 64, 10: None})
        self.assertEqual(
            [request["params"]["offset"] for request in session.requests],
            [0, 2, 4],
        )

    def test_fetch_chunk_hashes_rejects_mixed_hashes(self):
        session = FakeChunkStateSession({
            0: [
                {
                    "notice_id": 9,
                    "chunk_index": 0,
                    "content_hash": "a" * 64,
                },
                {
                    "notice_id": 9,
                    "chunk_index": 1,
                    "content_hash": "b" * 64,
                },
            ],
        })
        writer = SupabaseChunkWriter(
            url="https://example.supabase.co",
            secret_key="test-secret",
            session=session,
        )

        self.assertEqual(writer.fetch_chunk_hashes(), {9: None})

    def test_fetch_chunk_hashes_rejects_invalid_page_size(self):
        writer = SupabaseChunkWriter(
            url="https://example.supabase.co",
            secret_key="test-secret",
            session=FakeChunkStateSession({}),
        )

        with self.assertRaises(ValueError):
            writer.fetch_chunk_hashes(page_size=0)

    def test_apply_skips_model_loading_when_nothing_changed(self):
        notice = make_notice()
        repository = Mock()
        repository.fetch_notices.return_value = [notice]
        writer = Mock()
        writer.fetch_chunk_hashes.return_value = {
            notice["id"]: calculate_notice_hash(notice)
        }
        arguments = SimpleNamespace(
            model="test-model",
            batch_size=16,
            upload_batch_size=50,
            limit=None,
            apply=True,
            force=False,
            output_sql=Path("unused.sql"),
        )
        environment = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "test-publishable",
            "SUPABASE_SECRET_KEY": "test-secret",
        }

        with (
            patch.dict(os.environ, environment, clear=True),
            patch.object(chunk_notices, "parse_args", return_value=arguments),
            patch.object(chunk_notices, "load_dotenv"),
            patch.object(
                chunk_notices,
                "get_notice_repository",
                return_value=repository,
            ),
            patch.object(
                chunk_notices,
                "SupabaseChunkWriter",
                return_value=writer,
            ),
            patch.object(chunk_notices, "SentenceTransformer") as model_class,
        ):
            chunk_notices.main()

        model_class.assert_not_called()
        writer.replace_chunks.assert_not_called()

    def test_create_chunk_drafts_respects_token_limit(self):
        drafts = create_chunk_drafts(
            notices=[make_notice("가" * 1000)],
            tokenizer=FakeTokenizer(),
            max_sequence_tokens=512,
        )

        self.assertGreater(len(drafts), 2)
        self.assertEqual(
            [draft["chunk_index"] for draft in drafts],
            list(range(len(drafts))),
        )
        self.assertTrue(all(draft["token_count"] <= 512 for draft in drafts))

    def test_generate_rows_and_manifest(self):
        rows = generate_chunk_rows([make_notice()], FakeModel())
        manifest = get_chunk_manifest(rows)

        self.assertEqual(len(rows[0]["embedding"]), EMBEDDING_DIMENSION)
        self.assertEqual(rows[0]["embedding"][0], 1.0)
        self.assertEqual(manifest, [{"notice_id": 9, "chunk_count": 1}])

    def test_write_chunk_sql_contains_upsert_and_cleanup(self):
        rows = generate_chunk_rows([make_notice()], FakeModel())

        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "chunks.sql"
            write_chunk_sql(rows, output_path)
            sql = output_path.read_text(encoding="utf-8")

        self.assertIn("on conflict (notice_id, chunk_index)", sql)
        self.assertIn("embedding::text::public.vector", sql)
        self.assertIn("chunks.chunk_index >= manifest.chunk_count", sql)


if __name__ == "__main__":
    unittest.main()
