import os
import unittest
from unittest.mock import patch

from rag.src.db import (
    AliasRepositoryError,
    JsonNoticeRepository,
    SupabaseAliasRepository,
    SupabaseChunkRepository,
    SupabaseNoticeRepository,
    get_notice_repository,
    get_rag_search_source,
    validate_aliases,
)


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        return None

    def json(self):
        return self.rows


class FakeSession:
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


class FakeRpcSession:
    def __init__(self, responses):
        self.responses = responses
        self.requests = []

    def post(self, url, headers, json, timeout):
        rpc_name = url.rsplit("/", 1)[-1]
        self.requests.append({
            "url": url,
            "headers": headers,
            "json": json,
            "timeout": timeout,
        })
        return FakeResponse(self.responses[rpc_name])


class FakeGetSession:
    def __init__(self, rows):
        self.rows = rows
        self.requests = []

    def get(self, url, headers, params, timeout):
        self.requests.append({
            "url": url,
            "headers": headers,
            "params": params,
            "timeout": timeout,
        })
        return FakeResponse(self.rows)


def build_notice(notice_id):
    return {
        "id": notice_id,
        "source_notice_id": str(150000 + notice_id),
        "title": f"공지 {notice_id}",
        "url": f"https://example.com/{notice_id}",
        "category": None,
        "content": "공지 본문",
        "published_at": "2026-07-01",
    }


class SupabaseNoticeRepositoryTests(unittest.TestCase):
    def test_fetches_all_pages_without_renaming_columns(self):
        session = FakeSession({
            0: [build_notice(1), build_notice(2)],
            2: [build_notice(3)],
        })
        repository = SupabaseNoticeRepository(
            url="https://example.supabase.co",
            key="test-key",
            session=session,
            page_size=2,
        )

        notices = repository.fetch_notices()

        self.assertEqual([notice["id"] for notice in notices], [1, 2, 3])
        self.assertIn("source_notice_id", notices[0])
        self.assertIn("published_at", notices[0])
        self.assertNotIn("source_id", notices[0])
        self.assertNotIn("posted_at", notices[0])
        self.assertEqual(len(session.requests), 2)
        self.assertEqual(session.requests[0]["headers"], {"apikey": "test-key"})

    def test_fetches_single_notice_by_id(self):
        session = FakeGetSession([build_notice(7)])
        repository = SupabaseNoticeRepository(
            url="https://example.supabase.co",
            key="test-key",
            session=session,
        )

        notice = repository.fetch_notice(7)

        self.assertEqual(notice["id"], 7)
        self.assertEqual(session.requests[0]["params"]["id"], "eq.7")
        self.assertEqual(session.requests[0]["params"]["limit"], 1)


class SupabaseAliasRepositoryTests(unittest.TestCase):
    def test_fetches_alias_dictionary_rows(self):
        rows = [
            {"id": 1, "alias": "배알골", "meaning": "배OO 교수의 알고리즘 과목"},
            {"id": 2, "alias": "과사", "meaning": "컴퓨터공학과 학과사무실"},
        ]
        session = FakeGetSession(rows)
        repository = SupabaseAliasRepository(
            url="https://example.supabase.co",
            key="test-key",
            session=session,
        )

        aliases = repository.fetch_aliases()

        self.assertEqual(aliases, rows)
        self.assertTrue(session.requests[0]["url"].endswith("/rest/v1/aliases"))
        self.assertEqual(
            session.requests[0]["params"]["select"],
            "id,alias,meaning",
        )

    def test_rejects_duplicate_alias_rows(self):
        rows = [
            {"id": 1, "alias": "알골", "meaning": "알고리즘"},
            {"id": 2, "alias": "알골", "meaning": "알고리즘 과목"},
        ]

        with self.assertRaises(AliasRepositoryError):
            validate_aliases(rows)


class JsonNoticeRepositoryTests(unittest.TestCase):
    def test_sample_json_uses_supabase_column_names(self):
        notices = JsonNoticeRepository().fetch_notices()

        self.assertGreater(len(notices), 0)
        self.assertIn("source_notice_id", notices[0])
        self.assertIn("published_at", notices[0])

    def test_can_force_json_repository(self):
        repository = get_notice_repository(source="json")

        self.assertIsInstance(repository, JsonNoticeRepository)


class SupabaseChunkRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.semantic_row = {
            "chunk_id": 100,
            "notice_id": 10,
            "chunk_index": 0,
            "content_text": "신청 기간은 6월 22일까지다.",
            "semantic_score": 0.82,
            "title": "장학금 신청 안내",
            "category": "장학/근로",
            "published_at": "2026-05-22",
            "url": "https://example.com/10",
        }
        self.keyword_row = {
            **self.semantic_row,
            "keyword_score": 1.0,
            "matched_keywords": ["장학금", "신청"],
        }
        self.keyword_row.pop("semantic_score")
        self.session = FakeRpcSession({
            "match_notice_chunks": [self.semantic_row],
            "search_notice_chunks_keyword": [self.keyword_row],
        })
        self.repository = SupabaseChunkRepository(
            url="https://example.supabase.co",
            key="test-key",
            session=self.session,
        )

    def test_calls_semantic_rpc_with_contract_payload(self):
        rows = self.repository.match_notice_chunks(
            query_embedding=[0.1, 0.2],
            match_count=20,
            category_filter="장학/근로",
            deadline_from="2026-07-01T00:00:00+09:00",
            exclude_notice_ids=[1, 2],
        )

        self.assertEqual(rows, [self.semantic_row])
        request = self.session.requests[0]
        self.assertTrue(request["url"].endswith("/rpc/match_notice_chunks"))
        self.assertEqual(request["json"], {
            "query_embedding": [0.1, 0.2],
            "match_count": 20,
            "category_filter": "장학/근로",
            "deadline_from": "2026-07-01T00:00:00+09:00",
            "exclude_notice_ids": [1, 2],
        })

    def test_calls_keyword_rpc_with_contract_payload(self):
        rows = self.repository.search_notice_chunks_keyword(
            search_keywords=["장학금", "신청"],
            match_count=20,
            exclude_notice_ids=(3,),
        )

        self.assertEqual(rows, [self.keyword_row])
        request = self.session.requests[0]
        self.assertTrue(
            request["url"].endswith("/rpc/search_notice_chunks_keyword")
        )
        self.assertEqual(request["json"]["search_keywords"], ["장학금", "신청"])
        self.assertEqual(request["json"]["exclude_notice_ids"], [3])

    def test_search_source_accepts_explicit_modes(self):
        self.assertEqual(get_rag_search_source(source="notices"), "notices")
        self.assertEqual(get_rag_search_source(source="chunks"), "chunks")

    def test_search_source_uses_chunks_when_supabase_is_configured(self):
        environment = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "test-key",
        }

        with patch("rag.src.db.load_dotenv"), patch.dict(
            os.environ,
            environment,
            clear=True,
        ):
            self.assertEqual(get_rag_search_source(), "chunks")

    def test_search_source_uses_notices_without_supabase(self):
        with patch("rag.src.db.load_dotenv"), patch.dict(
            os.environ,
            {},
            clear=True,
        ):
            self.assertEqual(get_rag_search_source(), "notices")


if __name__ == "__main__":
    unittest.main()
