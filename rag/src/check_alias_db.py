from __future__ import annotations

import argparse
from collections.abc import Sequence

if __package__:
    from .db import AliasRepositoryError, get_alias_repository
else:
    from db import AliasRepositoryError, get_alias_repository


def print_alias_preview(alias_rows: list[dict], limit: int) -> None:
    if not alias_rows:
        print(
            "현재 SUPABASE_KEY로 조회 가능한 aliases 행이 없습니다."
        )
        print(
            "대시보드에 데이터가 있다면 public.aliases의 SELECT RLS 정책, "
            "스키마, 또는 .env의 SUPABASE_URL을 확인하세요."
        )
        return

    print(f"샘플 {min(limit, len(alias_rows))}개:")
    for row in alias_rows[:limit]:
        print(f"- {row['alias']} -> {row['meaning']}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Supabase aliases 은어 DB 연결 상태를 확인합니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="출력할 샘플 은어 개수입니다. 기본값은 5입니다.",
    )
    args = parser.parse_args(argv)

    try:
        alias_rows = get_alias_repository().fetch_aliases()
    except AliasRepositoryError as error:
        print("은어 DB 연결 실패")
        print(f"원인: {error}")
        return 1

    print("은어 DB REST 연결 성공")
    print(f"현재 key로 조회 가능한 aliases 행 수: {len(alias_rows)}")
    print_alias_preview(alias_rows, max(args.limit, 0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
