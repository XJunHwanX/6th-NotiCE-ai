/**
 * 챗봇 API 클라이언트 (클라이언트 전용).
 * FastAPI 백엔드(`POST /api/chat`)를 호출합니다. 대화 상태(state)는 서버가 준
 * 값을 그대로 되돌려주기만 하면 되는 불투명 값이라 타입을 열어 둡니다.
 */

export type ChatSource = {
  id: string | number | null;
  title: string;
  publishedAt?: string | null;
  url?: string | null;
};

/** 서버가 발급/갱신하는 대화 상태. 프론트는 해석하지 않고 그대로 왕복시킵니다. */
export type ChatState = Record<string, unknown> | null;

export type ChatResponse = {
  answer: string;
  state: ChatState;
  sources: ChatSource[];
};

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/+$/, "") ||
  "http://localhost:8000";

export async function sendChat(
  message: string,
  state: ChatState
): Promise<ChatResponse> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, state }),
    });
  } catch {
    throw new Error(
      "챗봇 서버에 연결할 수 없어요. 백엔드(uvicorn)가 실행 중인지 확인해 주세요."
    );
  }

  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      if (body?.detail) detail = `: ${body.detail}`;
    } catch {
      // 본문이 JSON이 아니면 상태 코드만 노출
    }
    throw new Error(`답변을 가져오지 못했어요 (${res.status})${detail}`);
  }

  return (await res.json()) as ChatResponse;
}

/** 빈 화면과 입력창 위 퀵칩에 공통으로 쓰는 자주 묻는 질문. */
export const SUGGESTED_QUESTIONS = [
  "이번 주 마감인 공지 있어?",
  "국가장학금 언제까지 신청해?",
  "졸업 요건이 궁금해",
  "이번 학기 수강신청 일정 알려줘",
  "요즘 올라온 채용·인턴 공지 있어?",
  "교내 대회나 공모전 뭐 있어?",
];
