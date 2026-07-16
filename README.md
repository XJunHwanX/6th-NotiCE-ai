# 6th-NotiCE-ai

홍익대학교 컴퓨터공학과 공지를 검색하고, 검색된 공지만 근거로 답변하는
한국어 RAG 챗봇 프로토타입입니다.

## 현재 기능

- 다국어 E5 임베딩과 키워드 점수를 결합한 하이브리드 검색
- 답변에 참고 공지 제목, 작성일, URL 강제 첨부
- 붙여 쓴 질문 보정과 학과 은어/약어 치환
- `kiwipiepy` 형태소 분석 기반 검색 키워드 추출
- 일반 검색, 후속 질문, 추가 결과, 마감일, 시험 장소, 요약 의도 분류
- `서류는?` 검색 질문 확장과 `다른 건 없어?` 결과 중복 제외
- 검색 결과는 제목 3개까지 먼저 보여주고 번호·서수·제목 선택 후 요약 제공
- Supabase 청크 벡터/키워드 RPC 클라이언트와 하이브리드 결과 병합

`.env`에 Supabase 설정이 있으면 `public.notices`를 사용하고, 설정이 없거나
`NOTICE_SOURCE=json`이면 `rag/data/sample_notices.json`을 사용합니다. 두 저장소는
실제 Supabase 컬럼명인 `source_notice_id`, `published_at`을 동일하게 사용합니다.

## 구현 현황 요약

| 영역 | 상태 | 현재 내용 |
| --- | --- | --- |
| Supabase 공지 조회 | 완료 | 운영 `notices` 220건과 실제 컬럼명 사용 |
| 청크 스키마 | 완료 | `notice_chunks`, `vector(384)`, HNSW, GIN, RLS 적용 |
| 청크 데이터 | 완료 | 공지 220건에서 청크 520건 생성 및 적재 |
| 변경분 재임베딩 | 완료 | `content_hash`가 다른 신규·변경·손상 공지만 재생성 |
| 검색 RPC | 완료 | 벡터 검색과 키워드 검색을 Supabase에서 실행 |
| 하이브리드 검색 | 완료 | 의미 점수 0.75와 키워드 점수 0.25 병합 |
| 대화형 결과 선택 | 완료 | 제목 최대 3개 표시 후 번호·서수·제목으로 선택 |
| 선택 공지 후속 질문 | 완료 | 선택 후 요약, 신청 방법, 서류, 상금 등의 질문 처리 |
| 마감일 추출·저장 | 미구현 | `notices.deadline`과 추출 파이프라인이 아직 없음 |
| 신청 가능 공지 필터 | 미구현 | 현재는 지난 공지도 검색될 수 있음 |
| 대화 상태 DB 저장 | 미구현 | 현재 실행 중인 프로세스 메모리에만 저장 |
| 과목·별칭·시험 일정 | 미구현 | 코드의 임시 별칭만 사용 중 |
| 답변 피드백 저장 | 미구현 | 테이블과 연결 코드가 아직 없음 |

현재 가장 중요한 제한은 마감일 데이터가 없다는 점입니다. `신청 가능한 대회`
같은 질문도 지금은 의미와 키워드 유사도로만 검색하므로 이미 마감된 공지가 나올
수 있습니다. LLM은 답변 요약을 담당하지만 신청 가능 여부를 확정하는 필터로
사용하지 않습니다.

## Supabase 데이터 구조

### 공통 규칙

- 아래의 `bigint` ID는 권장 타입입니다. 기존 `notices.id`가 `uuid`라면 모든
  외래키도 `uuid`로 통일합니다.
- 날짜와 시각은 `timestamptz`로 저장하고, 서비스에서는 `Asia/Seoul` 기준으로
  표시합니다. 작성일처럼 시각이 필요 없는 값만 `date`를 사용합니다.
- `service_role` 키는 챗봇 백엔드와 데이터 적재 작업에서만 사용하고
  프론트엔드에 전달하지 않습니다.
- 벡터 검색에는 `vector`, 한국어 부분 문자열 검색 보조에는 `pg_trgm`
  확장을 사용합니다.

```sql
create extension if not exists vector;
create extension if not exists pg_trgm;
```

테이블 관계:

```text
notices 1 ── N notice_chunks
notices 1 ── N notice_deadlines (추가 예정)
notices 1 ── N exam_schedules
courses 1 ── N aliases
courses 1 ── N exam_schedules
chat_sessions 1 ── N chat_messages
chat_messages 1 ── 0..1 answer_feedback
```

### `notices` (현재 운영 중)

크롤링한 공지 원문과 검색 필터용 메타데이터를 저장합니다. 공지 하나당 한
행만 존재하며, 챗봇의 출처 제목과 URL도 이 테이블에서 가져옵니다. 현재
Supabase에서 220건과 아래 7개 컬럼을 확인했습니다.

| 현재 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 내부 공지 ID |
| `source_notice_id` | `text` | O | 원본 사이트의 게시글 번호 |
| `title` | `text` | O | 공지 제목 |
| `url` | `text` | O | 사용자에게 보여줄 원문 URL |
| `category` | `text` | X | `학사`, `취업/인턴`, `장학/근로` 등의 분류 |
| `content` | `text` | O | 정제된 공지 본문 전체 |
| `published_at` | `date` | O | 공지 작성일 |

현재 `source_notice_id`와 `url` 중복은 없으며 `category`만 4건이 비어 있습니다.
다음 컬럼은 마감일 검색과 변경 감지를 위해 추가할 예정입니다.

| 추가 예정 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `application_start_at` | `timestamptz` | X | 신청 또는 접수 시작 시각 |
| `application_end_at` | `timestamptz` | X | 신청 또는 접수 종료 시각 |
| `deadline` | `timestamptz` | X | 마감 정렬에 사용할 대표 마감 시각 |
| `deadline_source` | `text` | X | `rules`, `manual` 중 추출 방식 |
| `deadline_status` | `text` | O | `extracted`, `not_found`, `ambiguous`, `inconsistent` |
| `deadline_confidence` | `numeric(4,3)` | X | 자동 추출 신뢰도, `0`부터 `1` 사이 |
| `deadline_reason` | `text` | X | 마감일로 판단한 원문 근거 문장 |
| `deadline_extracted_at` | `timestamptz` | X | 마지막 마감일 추출 시각 |
| `needs_review` | `boolean` | O | 마감일 또는 파싱 결과의 사람 검토 필요 여부 |
| `content_hash` | `text` | O | 공지 수정 여부를 판단할 본문 해시 |
| `created_at` | `timestamptz` | O | 최초 저장 시각 |
| `updated_at` | `timestamptz` | O | 마지막 수정 시각 |

권장 제약조건:

```sql
unique (source_notice_id)
unique (url)
```

`deadline`은 단순히 본문에서 가장 마지막에 등장하는 날짜로 정하지 않습니다.
`마감`, `까지`, `신청`, `접수`, `제출` 근처 날짜를 우선하고, 애매하면
`needs_review = true`로 저장합니다.

`deadline_confidence`에는 `check (deadline_confidence between 0 and 1)` 제약을
적용합니다.

마감일은 공지 단위 메타데이터이므로 `notice_chunks`에 추가하지 않습니다.
대표 신청 마감일과 검색 필터용 값은 `notices`에 저장하고, 접수·서류 제출·행사·
결과 발표처럼 일정이 여러 개이면 다음 `notice_deadlines` 테이블에 행을 나눠
저장합니다.

### `notice_deadlines` (추가 예정)

| 컬럼 | 권장 타입 | 설명 |
| --- | --- | --- |
| `id` | `bigint identity` | 일정 ID |
| `notice_id` | `bigint` | `notices.id` 외래키 |
| `event_type` | `text` | `application_start`, `application_end`, `event_start` 등 |
| `starts_at` | `timestamptz` | 기간 시작 시각 |
| `ends_at` | `timestamptz` | 기간 종료 시각 |
| `deadline_at` | `timestamptz` | 단일 마감 시각 |
| `evidence_text` | `text` | 날짜를 판단한 원문 문장 |
| `confidence` | `numeric(4,3)` | 규칙 기반 추출 신뢰도 |
| `source` | `text` | `regex`, `manual` 등 추출 방식 |
| `needs_review` | `boolean` | 사람 확인 필요 여부 |

초기 구현은 정규식으로 날짜가 있는 문장을 찾고 `dateparser`로 날짜를
`Asia/Seoul` 기준 `datetime`으로 변환합니다. `신청`, `접수`, `제출`, `까지`,
`마감` 등의 주변 단어로 역할을 판정하고 다음 검증을 통과한 값만 저장합니다.

```text
신청 시작 <= 신청 마감
신청 마감 <= 행사 시작
공지 작성일보다 과거인 신청 마감은 inconsistent
근거 문장이 없거나 날짜가 충돌하면 needs_review = true
```

신청 가능 상태는 고정해서 저장하지 않고 조회 시점에 계산합니다.

```text
upcoming: 현재 < application_start_at
open: application_start_at <= 현재 <= application_end_at
closed: 현재 > application_end_at
unknown: 검증된 마감일 없음
```

### 검색 모드

청크 테이블과 RPC가 준비되기 전후를 설정 하나로 전환합니다.

| `RAG_SEARCH_SOURCE` | 동작 |
| --- | --- |
| `notices` | 현재 방식. 공지 전체를 읽어 로컬에서 임베딩하고 검색 |
| `chunks` | 질문만 임베딩하고 Supabase의 두 청크 검색 RPC 호출 |

`RAG_SEARCH_SOURCE`를 생략하면 Supabase 설정이 있을 때 `chunks`, 없을 때
`notices`를 자동 선택합니다. 현재 운영 프로젝트는 청크와 RPC 검증을 마쳐
자동으로 `chunks` 모드를 사용합니다.

### `notice_chunks` (현재 운영 중)

RAG 검색용 청크와 임베딩을 저장합니다. 공지 원문은 `notices`에 보존하고,
긴 본문만 여러 청크로 나눕니다. 현재 공지 220건에서 생성한 청크 520건이
적재되어 있고, 모든 공지가 하나 이상의 청크와 연결되어 있습니다.

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 청크 ID |
| `notice_id` | `bigint` | O | `notices.id` 외래키 |
| `chunk_index` | `integer` | O | 같은 공지 안의 청크 순서, `0`부터 시작 |
| `content_text` | `text` | O | 메타데이터를 제외한 실제 본문 조각 |
| `chunk_text` | `text` | O | 제목과 메타데이터를 포함한 임베딩 대상 텍스트 |
| `embedding` | `vector(384)` | O | `multilingual-e5-small` 임베딩 |
| `token_count` | `integer` | O | 청크 크기 확인용 토큰 수 |
| `content_hash` | `text` | O | 이 청크를 만든 원본 공지의 해시 |
| `embedded_at` | `timestamptz` | O | 임베딩 생성 시각 |

관계와 제약조건:

```text
notice_chunks.notice_id -> notices.id ON DELETE CASCADE
unique (notice_id, chunk_index)
```

`chunk_text` 형식은 모든 청크에서 동일하게 유지합니다.

```text
제목: 2026-2학기 교내장학금 신청 안내
카테고리: 장학/근로
게시일: 2026-05-22
내용: 실제 본문 조각
```

청크 생성 규칙:

- 짧은 공지는 청크 한 개로 저장합니다.
- 긴 공지는 문장 경계를 기준으로 약 500~800자씩 나눕니다.
- 앞뒤 청크는 약 100자를 겹칩니다.
- 임베딩 입력은 `passage: {chunk_text}` 형식을 사용합니다.
- 모델은 `intfloat/multilingual-e5-small`, 출력은 384차원입니다.
- 임베딩 생성 시 `normalize_embeddings=True`를 사용합니다.
- 제목, 카테고리, 작성일, 본문으로 계산한 SHA-256 `content_hash`를 함께 저장합니다.
- `(notice_id, chunk_index)` 기준으로 upsert하고 더 이상 존재하지 않는 뒤쪽 청크는
  삭제합니다.

권장 검색 인덱스:

```sql
create index notice_chunks_embedding_hnsw_idx
on public.notice_chunks using hnsw (embedding public.vector_cosine_ops);

create index notice_chunks_text_trgm_idx
on public.notice_chunks using gin (chunk_text extensions.gin_trgm_ops);
```

### `courses`

과목명, 교수명, 분반을 구조화해서 저장합니다. `배알골`처럼 과목과 교수를
함께 가리키는 표현을 정확한 검색 조건으로 바꿀 때 사용합니다.

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 과목 개설 ID |
| `course_code` | `text` | X | 학수번호 |
| `course_name` | `text` | O | 공식 과목명 |
| `professor_name` | `text` | O | 담당 교수명 |
| `section` | `text` | X | 분반 |
| `semester` | `text` | O | 예: `2026-1` |
| `created_at` | `timestamptz` | O | 저장 시각 |

### `aliases`

학과 은어, 과목 약어, 건물 별칭을 공식 표현으로 변환하는 사전입니다.
현재 코드의 임시 사전은 Supabase 연결 후 이 테이블 데이터로 교체합니다.

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 별칭 ID |
| `alias` | `text` | O | 사용자가 입력하는 표현, 예: `배알골` |
| `canonical_text` | `text` | O | 공식 검색 표현 |
| `alias_type` | `text` | O | `course`, `professor`, `location`, `category` |
| `course_id` | `bigint` | X | 과목 별칭이면 `courses.id` 참조 |
| `active` | `boolean` | O | 현재 사용 여부 |
| `created_at` | `timestamptz` | O | 저장 시각 |

`alias`에는 대소문자와 앞뒤 공백을 정리한 값을 저장하고, 활성 별칭 안에서
중복되지 않도록 관리합니다.

### `exam_schedules`

시험 장소 공지의 표 데이터를 행 단위로 저장합니다. 시험 장소는 긴 공지
본문을 RAG로 찾는 것보다 이 테이블을 직접 조회하는 편이 정확합니다.

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 시험 일정 ID |
| `notice_id` | `bigint` | O | 출처인 `notices.id` |
| `course_id` | `bigint` | X | 매칭된 `courses.id` |
| `exam_type` | `text` | O | `중간`, `기말`, `퀴즈` 등 |
| `course_name` | `text` | O | 공지 표에 적힌 과목명 |
| `professor_name` | `text` | X | 공지 표에 적힌 교수명 |
| `section` | `text` | X | 분반 |
| `exam_date` | `date` | X | 시험 날짜 |
| `exam_time` | `time` | X | 시험 시간 |
| `exam_room` | `text` | O | 시험 장소 |
| `source_text` | `text` | O | 파싱 근거가 된 원본 표 행 |
| `needs_review` | `boolean` | O | 파싱 결과 검토 필요 여부 |

### `chat_sessions`와 `chat_messages`

`서류는?`, `다른 건 없어?` 같은 후속 질문을 처리하기 위한 대화 상태와
메시지 기록입니다.

`chat_sessions`:

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `uuid` | O | 세션 ID |
| `user_id` | `uuid` | X | 로그인 사용자가 있으면 사용자 ID |
| `last_search_query` | `text` | X | 추가 검색에 다시 사용할 검색 질문 |
| `last_category` | `text` | X | 직전 검색의 카테고리 필터 |
| `shown_notice_ids` | `bigint[]` | O | 이미 사용자에게 보여준 공지 ID |
| `created_at` | `timestamptz` | O | 세션 생성 시각 |
| `updated_at` | `timestamptz` | O | 마지막 대화 시각 |

`chat_messages`:

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `uuid` | O | 메시지 ID |
| `session_id` | `uuid` | O | `chat_sessions.id` 외래키 |
| `role` | `text` | O | `user` 또는 `assistant` |
| `content` | `text` | O | 원문 메시지 |
| `normalized_query` | `text` | X | 전처리와 후속 질문 확장을 거친 검색 질문 |
| `intent` | `text` | X | 분류된 질문 의도 |
| `referenced_notice_ids` | `bigint[]` | O | 답변 근거로 사용한 공지 ID |
| `created_at` | `timestamptz` | O | 메시지 생성 시각 |

최근 메시지 4~6개와 직전 `referenced_notice_ids`만 챗봇에 전달합니다. 전체
대화 기록을 매번 LLM에 넣지 않습니다.

### `answer_feedback`

답변의 도움 됨/안 됨 평가를 저장해 검색 기준값과 답변 품질을 개선할 때
사용합니다.

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 피드백 ID |
| `message_id` | `uuid` | O | 평가 대상 `chat_messages.id` |
| `rating` | `smallint` | O | 도움 됨 `1`, 도움 안 됨 `-1` |
| `comment` | `text` | X | 선택 입력 의견 |
| `created_at` | `timestamptz` | O | 피드백 생성 시각 |

`unique (message_id)`를 적용해 같은 답변에는 최신 평가 하나만 유지하는 것을
권장합니다.

### `suggested_questions` (선택)

추천 질문은 초기에는 챗봇 코드에서 현재 의도와 공지 내용으로 생성해도 됩니다.
운영자가 버튼 문구와 순서를 직접 관리해야 한다면 다음 테이블을 추가합니다.

| 컬럼 | 권장 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `id` | `bigint identity` | O | 추천 질문 ID |
| `intent` | `text` | O | 노출할 질문 의도 |
| `category` | `text` | X | 특정 공지 카테고리에만 노출할 때 사용 |
| `question_text` | `text` | O | 버튼에 표시하고 전송할 질문 |
| `display_order` | `integer` | O | 노출 순서 |
| `active` | `boolean` | O | 현재 사용 여부 |

### 접근 권한

- `notices`, `notice_chunks`, `courses`, `aliases`, `exam_schedules` 쓰기는
  크롤러와 관리 백엔드에만 허용합니다.
- 챗봇 서버는 필요한 테이블 읽기와 대화 기록 쓰기 권한만 사용합니다.
- 프론트엔드가 Supabase를 직접 호출한다면 `anon` 키와 RLS 정책을 사용하고,
  `service_role` 키는 어떤 경우에도 브라우저 코드에 넣지 않습니다.
- 로그인 기능이 있다면 사용자는 본인의 `chat_sessions`, `chat_messages`,
  `answer_feedback`만 읽고 쓸 수 있도록 RLS 정책을 설정합니다.

### 검색 RPC 계약

챗봇이 모든 임베딩을 다운로드하지 않도록 벡터 유사도 계산은 Supabase에서
수행합니다. [supabase/notice_chunks.sql](supabase/notice_chunks.sql)이 다음 두
RPC를 생성합니다.

```text
match_notice_chunks(
  query_embedding vector(384),
  match_count integer,
  category_filter text default null,
  deadline_from timestamptz default null,
  exclude_notice_ids bigint[] default '{}'
)
```

반환 필드:

| 필드 | 설명 |
| --- | --- |
| `chunk_id` | 검색된 청크 ID |
| `notice_id` | 원본 공지 ID |
| `chunk_index` | 주변 청크 조회에 사용할 순서 |
| `content_text` | LLM에 전달할 본문 조각 |
| `semantic_score` | 코사인 유사도 점수 |
| `title` | 출처 제목 |
| `category` | 카테고리 |
| `published_at` | 작성일 |
| `deadline` | 대표 마감 시각 |
| `url` | 출처 URL |

정확한 회사명, 강의실, 연구실명 검색을 위해 키워드 검색 RPC도 권장합니다.

```text
search_notice_chunks_keyword(
  search_keywords text[],
  match_count integer,
  category_filter text default null,
  exclude_notice_ids bigint[] default '{}'
)
```

이 함수는 위 반환 필드에 `keyword_score`와 `matched_keywords`를 추가합니다.
챗봇은 두 RPC 결과를 `chunk_id` 기준으로 합치고 다음 점수로 정렬합니다.

```text
hybrid_score = semantic_score * 0.75 + keyword_score * 0.25
```

RPC 반환 타입 권장값:

| 필드 | 권장 타입 |
| --- | --- |
| `chunk_id`, `notice_id` | `bigint` |
| `chunk_index` | `integer` |
| `content_text`, `title`, `category`, `url` | `text` |
| `published_at` | `date` |
| `deadline` | `timestamptz` |
| `semantic_score`, `keyword_score` | `double precision` |
| `matched_keywords` | `text[]` |

Python 코드는 함수명, 파라미터명, 반환 필드를 위 계약 그대로 사용합니다. DB의
이름이 다르면 PostgREST RPC 호출 또는 응답 검증 단계에서 오류가 발생합니다.
현재 `notices.deadline` 컬럼은 없으므로 `deadline`은 `null`을 반환하고
`deadline_from`은 다음 스키마 확장을 위해 예약되어 있습니다.

현재 완료 상태:

- [x] `notice_chunks` 컬럼과 제약조건 생성
- [x] 공지 220건을 청크 520건으로 분할하고 임베딩 적재
- [x] `vector(384)` HNSW와 `pg_trgm` GIN 인덱스 생성
- [x] `match_notice_chunks`, `search_notice_chunks_keyword` 생성
- [x] `anon`, `authenticated` 역할에 두 검색 함수 실행 권한 부여
- [x] 공개 키 REST 호출로 키워드 검색과 벡터 검색 검증

`notice_chunks` 직접 쓰기는 취소되어 있고, 읽기 역시 RLS를 우회하는
`security definer` 검색 함수로만 제공합니다.

### 청크 스키마와 적재

최초 구성 시 Supabase SQL Editor에서
[supabase/notice_chunks.sql](supabase/notice_chunks.sql)을 실행합니다. 이 파일은
컬럼, 제약조건, 인덱스, RLS, 검색 RPC를 함께 생성합니다.

청크 생성 결과를 SQL 파일로 검토하려면 다음 명령을 사용합니다.

```bash
rag/.venv/bin/python -m rag.src.chunk_notices
```

기본 출력은 `supabase/generated/notice_chunks_data.sql`이며 Git에서는 제외됩니다.
DB에 직접 반영하려면 크롤러 또는 관리 백엔드 환경에만 보관한 비밀 키를
설정합니다.

```env
SUPABASE_SECRET_KEY=sb_secret_your_key
```

```bash
rag/.venv/bin/python -m rag.src.chunk_notices --apply
```

이 명령은 `notices`를 읽고 500~800자 단위로 분할한 뒤 E5 임베딩을 생성해
`(notice_id, chunk_index)` 기준으로 upsert합니다. 적용 전에 기존 청크의
`content_hash`를 조회하므로 신규·변경 공지만 임베딩하고, 변경이 없으면 모델도
불러오지 않습니다. 해시가 섞였거나 청크 번호가 연속적이지 않은 공지도 손상된
상태로 판단해 다시 생성합니다.

임베딩 모델이나 청크 분할 규칙을 변경해 전체 공지를 다시 생성할 때만 다음
명령을 사용합니다.

```bash
rag/.venv/bin/python -m rag.src.chunk_notices --apply --force
```

일반 챗봇 실행에는 비밀 키가 필요하지 않고 `SUPABASE_KEY` 공개 키만 사용합니다.

### 데이터 적재 담당 범위

DB 및 데이터 적재 코드가 담당할 작업:

```text
공지 크롤링
-> source_notice_id 기준 upsert
-> content_hash로 변경 여부 확인
-> 마감일과 신청 기간 추출
-> 시험표가 있으면 exam_schedules 생성
-> 본문 청크 분할
-> 청크 임베딩 생성
-> notice_chunks 저장
```

챗봇 코드가 담당할 작업:

```text
질문 전처리와 별칭 치환
-> 질문 의도 분류
-> 질문 임베딩 생성
-> 벡터 RPC와 키워드 RPC 호출
-> 하이브리드 재정렬과 주변 청크 확장
-> LLM 답변 생성과 출처 첨부
-> 대화 상태와 피드백 저장
```

### 다음 구현 순서

1. `notices`에 신청 기간, 대표 마감일, 추출 상태, 근거 컬럼 추가
2. 여러 일정을 저장할 `notice_deadlines` 테이블과 제약조건 추가
3. 정규식과 `dateparser` 기반 한국어 날짜 후보 추출 코드 작성
4. 주변 단어 점수로 신청 마감·행사일·발표일 역할 분류
5. 날짜 순서, 작성일, 근거 문장 검증과 `needs_review` 처리
6. 기존 공지 220건 백필 후 사람이 표본 검수
7. `match_notice_chunks`가 `notices.deadline`을 반환하고 필터하도록 변경
8. `신청 가능한`, `현재 모집 중` 질문에서 현재 시각 필터 전달
9. 공지 크롤링 후 변경된 공지만 날짜 추출과 청크 재생성하도록 배치 연결
10. `chat_sessions`, `chat_messages`로 대화 상태 영속화
11. `courses`, `aliases`, `exam_schedules`, `answer_feedback` 순서로 확장

## 실행

레포 최상위 `.env`에 Gemini API 키를 설정합니다.

```env
GEMINI_API_KEY=your_api_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=sb_publishable_your_key
NOTICE_SOURCE=auto
RAG_SEARCH_SOURCE=chunks
```

`NOTICE_SOURCE=auto`는 Supabase 설정이 있으면 Supabase를 사용하고, 없으면
샘플 JSON을 사용합니다. 네트워크 없이 샘플 데이터로 실행하려면 `json`,
Supabase 설정 누락을 오류로 확인하려면 `supabase`로 지정합니다.

`RAG_SEARCH_SOURCE`를 생략하면 Supabase 설정이 있는 환경은 `chunks`, 없는
환경은 `notices`를 자동 선택합니다. 로컬 JSON 방식이나 청크 장애를 확인할
때는 `notices`로 명시할 수 있습니다.

가상환경에 의존성을 설치하고 실행합니다.

```bash
rag/.venv/bin/pip install -r rag/requirements.txt
rag/.venv/bin/python -m rag.src.search
```

첫 실행에는 `intfloat/multilingual-e5-small` 모델 다운로드를 위한 인터넷
연결이 필요합니다.

## 테스트

```bash
rag/.venv/bin/python -m unittest discover -s rag/tests -v
```
