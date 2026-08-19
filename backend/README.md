# NotiCE FastAPI 백엔드

프론트엔드의 챗봇 요청을 처리하고 웹 푸시 발송 파이프라인을 지원합니다.
푸시 구독은 현재 팀 합의에 따라 브라우저가 Supabase에 직접 upsert합니다.

## 1. 환경 설정

[`backend/.env.example`](.env.example)을 참고해 레포 최상위 `.env` 또는
`backend/.env`에 값을 설정합니다.

```env
CORS_ORIGINS=http://localhost:3000
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_publishable_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
GEMINI_API_KEY=your_gemini_api_key
VAPID_PUBLIC_KEY=your_vapid_public_key
NOTICE_SOURCE=supabase
RAG_SEARCH_SOURCE=chunks
```

VAPID 비밀키는 API 서버가 아니라 실제 발송을 수행하는 파이프라인 환경에만 둡니다.
PEM 비밀키 전체를 GitHub Actions의 `VAPID_PRIVATE_KEY` Repository Secret으로
등록하면 워크플로가 실행 중 `pipeline/private_key.pem`으로 복원합니다. 로컬에서는
같은 경로에 PEM 파일을 두고 `pipeline/.env`에 아래 경로를 설정합니다. `*.pem`은
레포의 `.gitignore`에 포함되어 있습니다.

```env
VAPID_PRIVATE_KEY_PATH=pipeline/private_key.pem
```

## 2. DB 스키마 설치

Supabase SQL Editor에서
[`../supabase/push_subscriptions.sql`](../supabase/push_subscriptions.sql)을
실행합니다. 이 SQL은 다음 테이블을 만듭니다.

- `push_subscriptions`
- `notification_deliveries`

두 테이블 모두 RLS가 활성화됩니다. `push_subscriptions`는 로그인 없는 프론트의
직접 저장을 위해 anon `SELECT/INSERT/UPDATE`가 허용되고,
`notification_deliveries`는 service-role 전용입니다.

## 3. 실행

```bash
python3 -m venv .venv
.venv/bin/pip install -c requirements.txt -r backend/requirements.txt
.venv/bin/uvicorn backend.app.main:app --reload --port 8000
```

- 상태 확인: `GET http://localhost:8000/health`
- Swagger 문서: `http://localhost:8000/docs`

## 4. API 계약

### 챗봇

```http
POST /api/chat
Content-Type: application/json
```

```json
{
  "message": "장학 공지 알려줘",
  "state": null
}
```

응답의 `state`를 브라우저에 보관했다가 다음 질문에 그대로 포함합니다.

### 푸시 구독 등록 또는 갱신

현재 프론트는 FastAPI 대신 Supabase 클라이언트로 직접 저장합니다.

```ts
const json = subscription.toJSON();

await supabase.from("push_subscriptions").upsert(
  {
    endpoint: json.endpoint,
    p256dh: json.keys?.p256dh,
    auth: json.keys?.auth,
    categories,
    enabled: categories.length > 0,
  },
  { onConflict: "endpoint" }
);
```

프론트의 영문 카테고리 ID는 DB 트리거가 파이프라인의 한글 카테고리로
자동 변환합니다. `POST /api/push/subscriptions`는 서버 경유 방식이 필요할 때
사용할 수 있는 대체 API로 유지합니다.

#### 서버 경유 대체 API

```http
POST /api/push/subscriptions
Content-Type: application/json
```

```json
{
  "subscription": {
    "endpoint": "https://push-service.example/subscription",
    "keys": {
      "p256dh": "browser-generated-key",
      "auth": "browser-generated-auth"
    }
  },
  "categories": ["academic", "scholarship"]
}
```

프론트 카테고리 ID는 API가 파이프라인의 한글 카테고리로 변환합니다. 반환되는
`subscriptionId`와 `managementToken`은 구독 설정 변경과 해지에 사용하므로
브라우저에 함께 보관합니다.

### 구독 설정 변경

```http
PATCH /api/push/subscriptions/{subscriptionId}
X-Subscription-Token: {managementToken}
Content-Type: application/json
```

```json
{
  "categories": ["career"],
  "enabled": true
}
```

### 구독 해지

```http
DELETE /api/push/subscriptions/{subscriptionId}
X-Subscription-Token: {managementToken}
```

### VAPID 공개키

```http
GET /api/push/vapid-public-key
```

현재 프론트엔드는 `NEXT_PUBLIC_VAPID_PUBLIC_KEY` 환경변수도 지원합니다.

## 5. 테스트

```bash
.venv/bin/python -m unittest discover -s backend/tests -v
.venv/bin/python -m unittest discover -s rag/tests -v
```

## 6. Render 무료 배포

레포 최상위의 `render.yaml`을 Blueprint로 연결하면 무료 Web Service가
생성됩니다. `RAG_RETRIEVAL_MODE=hybrid`는 로컬 모델을 적재하지 않고
Gemini Embedding API의 의미 임베딩과 키워드 검색을 함께 사용합니다.
검색 결과는 `rag/src/search.py`의 의미·키워드 임계값으로 관련성을 판정합니다.
임계값을 통과한 공지가 하나이거나 시험 관련 질문이면 바로 답변하고, 여러 공지가
통과하면 관련 공지 카드를 표시합니다.

기존 `notice_chunks`가 E5 벡터라면 배포 전에 Gemini 벡터로 한 번 갱신합니다.

```bash
python pipeline/reembed_notice_chunks.py
```

Blueprint 생성 화면에서 `sync: false`로 선언된 다음 값을 입력합니다.

```text
CORS_ORIGINS
SUPABASE_URL
SUPABASE_KEY
SUPABASE_SERVICE_ROLE_KEY
GEMINI_API_KEY
VAPID_PUBLIC_KEY
```

`CORS_ORIGINS`에는 우선 `http://localhost:3000`을 넣고, 프론트 배포 후 실제
프론트 주소로 변경합니다. `VAPID_PRIVATE_KEY`는 Render에 넣지 않습니다.

배포 후 아래 주소로 확인합니다.

```text
GET https://notice-api-hongik.onrender.com/health
GET https://notice-api-hongik.onrender.com/docs
```

## 7. Hugging Face Spaces 배포

레포 최상위의 `Dockerfile`은 Hugging Face Docker Space와 일반 Docker
호스팅에서 사용할 수 있습니다. Space 생성 시 SDK를 `Docker`, 무료 하드웨어를
`CPU Basic`으로 선택합니다. 컨테이너는 기본적으로 7860 포트에서 실행되며,
호스팅 서비스가 `PORT`를 제공하면 해당 값을 우선 사용합니다.

### Secrets

```text
SUPABASE_SERVICE_ROLE_KEY
GEMINI_API_KEY
```

### Variables

```text
APP_ENV=production
CORS_ORIGINS=https://your-frontend.example
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your_publishable_or_anon_key
VAPID_PUBLIC_KEY=your_vapid_public_key
NOTICE_SOURCE=supabase
RAG_SEARCH_SOURCE=chunks
```

`VAPID_PRIVATE_KEY`는 API 서버에 넣지 않습니다. 실제 푸시 발송을 실행하는
GitHub Actions Repository Secret으로만 관리합니다.

배포 후 아래 주소로 동작을 확인합니다.

```text
GET https://<space-subdomain>.hf.space/health
GET https://<space-subdomain>.hf.space/docs
```
