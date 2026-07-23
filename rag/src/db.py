from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

import requests
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
RAG_DIR = Path(__file__).resolve().parent.parent
DEFAULT_JSON_PATH = RAG_DIR / "data" / "sample_notices.json"

SUPABASE_NOTICE_COLUMNS = (
    "id",
    "source_notice_id",
    "title",
    "url",
    "category",
    "content",
    "published_at",
    "deadline",
)

SUPABASE_ALIAS_COLUMNS = (
    "id",
    "alias",
    "meaning",
)


class NoticeRepositoryError(RuntimeError):
    """공지 저장소를 읽지 못했을 때 발생하는 오류입니다."""


class ChunkRepositoryError(RuntimeError):
    """청크 검색 RPC를 호출하지 못했을 때 발생하는 오류입니다."""


class AliasRepositoryError(RuntimeError):
    """은어 저장소를 읽지 못했을 때 발생하는 오류입니다."""


class NoticeRepository(Protocol):
    source_name: str

    def fetch_notices(self) -> list[dict]: ...

    def fetch_notice(self, notice_id: object) -> dict | None: ...


class AliasRepository(Protocol):
    def fetch_aliases(self) -> list[dict]: ...


class ChunkRepository(Protocol):
    def match_notice_chunks(
        self,
        query_embedding: list[float],
        match_count: int,
        category_filter: str | None = None,
        deadline_from: str | None = None,
        exclude_notice_ids: tuple | list | set | None = None,
    ) -> list[dict]: ...

    def search_notice_chunks_keyword(
        self,
        search_keywords: list[str],
        match_count: int,
        category_filter: str | None = None,
        deadline_from: str | None = None,
        exclude_notice_ids: tuple | list | set | None = None,
    ) -> list[dict]: ...


def validate_notices(notices: object) -> list[dict]:
    if not isinstance(notices, list):
        raise NoticeRepositoryError("공지 데이터는 배열 형태여야 합니다.")

    required_fields = {
        "id",
        "source_notice_id",
        "title",
        "url",
        "content",
        "published_at",
    }

    for index, notice in enumerate(notices):
        if not isinstance(notice, dict):
            raise NoticeRepositoryError(
                f"공지 {index}번 데이터가 객체 형태가 아닙니다."
            )

        missing_fields = required_fields - notice.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise NoticeRepositoryError(
                f"공지 {index}번 데이터에 필수 컬럼이 없습니다: {missing}"
            )

    return notices


def validate_aliases(aliases: object) -> list[dict]:
    if not isinstance(aliases, list):
        raise AliasRepositoryError("은어 데이터는 배열 형태여야 합니다.")

    required_fields = {"id", "alias", "meaning"}
    seen_aliases = set()

    for index, alias_row in enumerate(aliases):
        if not isinstance(alias_row, dict):
            raise AliasRepositoryError(
                f"은어 {index}번 데이터가 객체 형태가 아닙니다."
            )

        missing_fields = required_fields - alias_row.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise AliasRepositoryError(
                f"은어 {index}번 데이터에 필수 컬럼이 없습니다: {missing}"
            )

        alias = alias_row["alias"]
        meaning = alias_row["meaning"]

        if not isinstance(alias, str) or not alias.strip():
            raise AliasRepositoryError(
                f"은어 {index}번의 alias가 비어 있습니다."
            )

        if alias != alias.strip():
            raise AliasRepositoryError(
                f"은어 {index}번의 alias 앞뒤에 공백이 있습니다."
            )

        if not isinstance(meaning, str) or not meaning.strip():
            raise AliasRepositoryError(
                f"은어 {index}번의 meaning이 비어 있습니다."
            )

        if alias in seen_aliases:
            raise AliasRepositoryError(f"중복된 은어가 있습니다: {alias}")

        seen_aliases.add(alias)

    return aliases


class JsonNoticeRepository:
    source_name = "sample JSON"

    def __init__(self, path: Path = DEFAULT_JSON_PATH) -> None:
        self.path = path

    def fetch_notices(self) -> list[dict]:
        if not self.path.exists():
            raise NoticeRepositoryError(
                f"공지 데이터 파일을 찾을 수 없습니다: {self.path}"
            )

        try:
            with self.path.open("r", encoding="utf-8") as file:
                notices = json.load(file)
        except (OSError, json.JSONDecodeError) as error:
            raise NoticeRepositoryError(
                f"공지 JSON을 읽지 못했습니다: {error}"
            ) from error

        return validate_notices(notices)

    def fetch_notice(self, notice_id: object) -> dict | None:
        for notice in self.fetch_notices():
            if notice.get("id") == notice_id:
                return notice

        return None


class SupabaseNoticeRepository:
    source_name = "Supabase"

    def __init__(
        self,
        url: str,
        key: str,
        session: requests.Session | None = None,
        page_size: int = 1000,
    ) -> None:
        if not url or not key:
            raise NoticeRepositoryError(
                "SUPABASE_URL 또는 SUPABASE_KEY가 없습니다."
            )

        self.url = url.rstrip("/")
        self.key = key
        self.session = session or requests.Session()
        self.page_size = page_size

    def fetch_notices(self) -> list[dict]:
        notices = []
        offset = 0

        while True:
            try:
                response = self.session.get(
                    f"{self.url}/rest/v1/notices",
                    headers={"apikey": self.key},
                    params={
                        "select": ",".join(SUPABASE_NOTICE_COLUMNS),
                        "order": "id.asc",
                        "limit": self.page_size,
                        "offset": offset,
                    },
                    timeout=20,
                )
                response.raise_for_status()
                page = response.json()
            except (requests.RequestException, ValueError) as error:
                raise NoticeRepositoryError(
                    f"Supabase notices 조회에 실패했습니다: {error}"
                ) from error

            if not isinstance(page, list):
                raise NoticeRepositoryError(
                    "Supabase notices 응답이 배열 형태가 아닙니다."
                )

            notices.extend(page)

            if len(page) < self.page_size:
                break

            offset += self.page_size

        return validate_notices(notices)

    def fetch_notice(self, notice_id: object) -> dict | None:
        try:
            response = self.session.get(
                f"{self.url}/rest/v1/notices",
                headers={"apikey": self.key},
                params={
                    "select": ",".join(SUPABASE_NOTICE_COLUMNS),
                    "id": f"eq.{notice_id}",
                    "limit": 1,
                },
                timeout=20,
            )
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError) as error:
            raise NoticeRepositoryError(
                f"Supabase 공지 상세 조회에 실패했습니다: {error}"
            ) from error

        notices = validate_notices(rows)
        return notices[0] if notices else None


class SupabaseAliasRepository:
    def __init__(
        self,
        url: str,
        key: str,
        session: requests.Session | None = None,
    ) -> None:
        if not url or not key:
            raise AliasRepositoryError(
                "SUPABASE_URL 또는 SUPABASE_KEY가 없습니다."
            )

        self.url = url.rstrip("/")
        self.key = key
        self.session = session or requests.Session()

    def fetch_aliases(self) -> list[dict]:
        try:
            response = self.session.get(
                f"{self.url}/rest/v1/aliases",
                headers={"apikey": self.key},
                params={
                    "select": ",".join(SUPABASE_ALIAS_COLUMNS),
                    "order": "id.asc",
                },
                timeout=20,
            )
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError) as error:
            raise AliasRepositoryError(
                f"Supabase aliases 조회에 실패했습니다: {error}"
            ) from error

        return validate_aliases(rows)


SEMANTIC_CHUNK_FIELDS = {
    "chunk_id",
    "notice_id",
    "chunk_index",
    "content_text",
    "semantic_score",
    "title",
    "category",
    "published_at",
    "deadline",
    "url",
}

KEYWORD_CHUNK_FIELDS = {
    "chunk_id",
    "notice_id",
    "chunk_index",
    "content_text",
    "keyword_score",
    "matched_keywords",
    "title",
    "category",
    "published_at",
    "deadline",
    "url",
}


def validate_chunk_rows(
    rows: object,
    required_fields: set[str],
    rpc_name: str,
) -> list[dict]:
    if not isinstance(rows, list):
        raise ChunkRepositoryError(
            f"{rpc_name} 응답은 배열 형태여야 합니다."
        )

    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ChunkRepositoryError(
                f"{rpc_name} 응답 {index}번이 객체 형태가 아닙니다."
            )

        missing_fields = required_fields - row.keys()
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            raise ChunkRepositoryError(
                f"{rpc_name} 응답에 필수 필드가 없습니다: {missing}"
            )

    return rows


class SupabaseChunkRepository:
    def __init__(
        self,
        url: str,
        key: str,
        session: requests.Session | None = None,
    ) -> None:
        if not url or not key:
            raise ChunkRepositoryError(
                "SUPABASE_URL 또는 SUPABASE_KEY가 없습니다."
            )

        self.url = url.rstrip("/")
        self.key = key
        self.session = session or requests.Session()

    def _call_rpc(
        self,
        rpc_name: str,
        payload: dict,
        required_fields: set[str],
    ) -> list[dict]:
        try:
            response = self.session.post(
                f"{self.url}/rest/v1/rpc/{rpc_name}",
                headers={
                    "apikey": self.key,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=20,
            )
            response.raise_for_status()
            rows = response.json()
        except (requests.RequestException, ValueError) as error:
            raise ChunkRepositoryError(
                f"Supabase {rpc_name} 호출에 실패했습니다: {error}"
            ) from error

        return validate_chunk_rows(rows, required_fields, rpc_name)

    def match_notice_chunks(
        self,
        query_embedding: list[float],
        match_count: int,
        category_filter: str | None = None,
        deadline_from: str | None = None,
        exclude_notice_ids: tuple | list | set | None = None,
    ) -> list[dict]:
        return self._call_rpc(
            rpc_name="match_notice_chunks",
            payload={
                "query_embedding": query_embedding,
                "match_count": match_count,
                "category_filter": category_filter,
                "deadline_from": deadline_from,
                "exclude_notice_ids": list(exclude_notice_ids or ()),
            },
            required_fields=SEMANTIC_CHUNK_FIELDS,
        )

    def search_notice_chunks_keyword(
        self,
        search_keywords: list[str],
        match_count: int,
        category_filter: str | None = None,
        deadline_from: str | None = None,
        exclude_notice_ids: tuple | list | set | None = None,
    ) -> list[dict]:
        return self._call_rpc(
            rpc_name="search_notice_chunks_keyword",
            payload={
                "search_keywords": search_keywords,
                "match_count": match_count,
                "category_filter": category_filter,
                "deadline_from": deadline_from,
                "exclude_notice_ids": list(exclude_notice_ids or ()),
            },
            required_fields=KEYWORD_CHUNK_FIELDS,
        )


def get_notice_repository(source: str | None = None) -> NoticeRepository:
    load_dotenv(ROOT_DIR / ".env")

    selected_source = (source or os.getenv("NOTICE_SOURCE", "auto")).lower()

    if selected_source not in {"auto", "supabase", "json"}:
        raise NoticeRepositoryError(
            "NOTICE_SOURCE는 auto, supabase, json 중 하나여야 합니다."
        )

    supabase_url = os.getenv("SUPABASE_URL")
    supabase_key = os.getenv("SUPABASE_KEY")

    if selected_source == "supabase" or (
        selected_source == "auto" and supabase_url and supabase_key
    ):
        return SupabaseNoticeRepository(
            url=supabase_url or "",
            key=supabase_key or "",
        )

    return JsonNoticeRepository()


def get_chunk_repository() -> ChunkRepository:
    load_dotenv(ROOT_DIR / ".env")

    return SupabaseChunkRepository(
        url=os.getenv("SUPABASE_URL", ""),
        key=os.getenv("SUPABASE_KEY", ""),
    )


def get_alias_repository() -> AliasRepository:
    load_dotenv(ROOT_DIR / ".env")

    return SupabaseAliasRepository(
        url=os.getenv("SUPABASE_URL", ""),
        key=os.getenv("SUPABASE_KEY", ""),
    )


def get_rag_search_source(source: str | None = None) -> str:
    load_dotenv(ROOT_DIR / ".env")

    configured_source = source or os.getenv("RAG_SEARCH_SOURCE")

    if configured_source:
        selected_source = configured_source.lower()
    elif os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"):
        selected_source = "chunks"
    else:
        selected_source = "notices"

    if selected_source not in {"notices", "chunks"}:
        raise NoticeRepositoryError(
            "RAG_SEARCH_SOURCE는 notices 또는 chunks여야 합니다."
        )

    return selected_source
