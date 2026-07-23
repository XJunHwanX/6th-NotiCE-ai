# NotiCE RAG 챗봇

홍익대학교 컴퓨터공학과 공지를 검색하고, 검색된 공지만 근거로 답변하는 한국어
RAG 챗봇입니다. 이 디렉터리는 질문 처리와 검색, 답변 생성을 담당합니다.
공지 수집과 청크 생성·적재는 크롤링 파이프라인의 책임입니다.

## 처리 흐름

```text
사용자 질문
→ 붙여쓰기 보정 및 aliases 은어 확장
→ LLM 라우터와 규칙 기반 검증
→ 질문 E5 임베딩 생성
→ Supabase 벡터·키워드 검색
→ 관련 공지 선택 및 전체 본문 조회
→ 검색된 공지만 사용해 Gemini 답변 생성
→ 코드에서 출처 첨부
```

LLM 라우터는 일반 공지, 신청 가능한 공지, 시험 공지, 선택 공지 후속 질문,
일반 대화, 추가 확인 질문 중 하나를 구조화된 JSON으로 반환합니다. 시험 질문과
번호 선택처럼 확실한 흐름은 코드 규칙으로 다시 검증하며, LLM 호출에 실패하면
규칙 기반 라우터로 복귀합니다.

검색은 의미 점수 0.75와 키워드 점수 0.25를 결합합니다. 여러 공지가 비슷하게
검색되면 제목을 최대 3개 보여주고 사용자가 번호나 제목으로 선택하도록 합니다.
선택 후에는 `notices.content`의 전체 본문을 다시 조회해 답변합니다.

## 크롤링 파이프라인과의 계약

크롤링 담당 파이프라인은 공지 청크와 passage 임베딩을 생성하고 최신 상태로
유지해야 합니다. 챗봇은 해당 데이터를 읽기만 합니다.

| 항목 | 계약 |
| --- | --- |
| 임베딩 모델 | `intfloat/multilingual-e5-small` |
| 임베딩 차원 | 384 |
| 청크 입력 형식 | `passage: {청크 텍스트}` |
| 질문 입력 형식 | `query: {사용자 질문}` |
| 정규화 | passage와 query 모두 L2 정규화 |

`notice_chunks`의 최소 필수 컬럼은 다음과 같습니다.

```text
id            bigint
notice_id     bigint
chunk_index   integer
content_text  text
embedding     vector(384)
```

연결되는 `notices`에는 다음 컬럼이 필요합니다.

```text
id, source_notice_id, title, url, category, content, published_at, deadline
```

`category`는 현재 크롤링 파이프라인과 동일한 `text[]` 계약을 사용합니다.
`deadline`은 nullable이지만 신청 가능 공지 검색을 사용하려면 크롤링 파이프라인이
실제 마감 시각을 `timestamptz`로 적재해야 합니다. 신규·수정 공지 재임베딩과 삭제된
공지의 오래된 청크 정리도 크롤링 파이프라인이 담당합니다.

크롤링 파이프라인이 `notice_chunks`를 만든 뒤
[`../supabase/rag_search.sql`](../supabase/rag_search.sql)을 Supabase SQL Editor에서
실행하면 챗봇이 사용하는 검색 RPC와 읽기 권한이 설치됩니다.

## 환경 설정

예시 파일을 레포 최상위 `.env`로 복사하고 실제 값을 입력합니다.

```bash
cp rag/.env.example .env
```

```env
GEMINI_API_KEY=your_gemini_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_supabase_publishable_key
NOTICE_SOURCE=supabase
RAG_SEARCH_SOURCE=chunks
```

챗봇은 공개 가능한 Supabase publishable key로 읽기 RPC만 호출합니다. 청크 적재에
사용하는 secret 또는 service-role key는 챗봇 환경에 두지 않습니다.

## 설치 및 실행

크롤링 파이프라인의 루트 `requirements.txt`와 분리된 가상환경을 권장합니다.

```bash
python3 -m venv rag/.venv
rag/.venv/bin/pip install -r rag/requirements.txt
rag/.venv/bin/python -m rag.src.search
```

은어 테이블 연결만 확인하려면 다음 명령을 사용합니다.

```bash
rag/.venv/bin/python -m rag.src.check_alias_db
```

## 로컬 샘플 모드

Supabase 없이 검색 흐름을 확인할 때는 다음 값을 사용합니다.

```env
NOTICE_SOURCE=json
RAG_SEARCH_SOURCE=notices
```

이 모드는 `rag/data/sample_notices.json`을 메모리에서 임베딩해 검색하며 DB에 청크를
생성하거나 쓰지 않습니다.

## 테스트

```bash
rag/.venv/bin/python -m unittest discover -s rag/tests -v
```

## 현재 제한

- 대화 상태는 실행 중인 프로세스 메모리에만 저장됩니다.
- 신청 가능 공지 검색 품질은 `notices.deadline` 적재 상태에 의존합니다.
- 시험 일정은 별도 테이블이 아니라 최신 시험 공지의 전체 본문과 표를 읽습니다.
- 검색 가중치와 임계값은 대표 질문 평가 세트로 추가 조정해야 합니다.
