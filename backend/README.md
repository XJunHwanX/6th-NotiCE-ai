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
.venv/bin/pip install -r requirements.txt
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
