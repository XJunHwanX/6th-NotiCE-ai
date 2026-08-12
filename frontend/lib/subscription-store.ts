import { CATEGORIES, type CategoryId } from "./categories";

/**
 * 구독한 알림 카테고리를 브라우저 localStorage에 보관합니다.
 * 백엔드 구독 저장 API가 준비되면 이 로컬 저장을 서버 값과 동기화하도록
 * 확장하면 됩니다. (지금은 로컬이 단일 출처)
 */
const STORAGE_KEY = "notice:subscribed-categories";

const VALID_IDS = new Set<string>(CATEGORIES.map((c) => c.id));

export function getSubscribedCategories(): CategoryId[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (v): v is CategoryId => typeof v === "string" && VALID_IDS.has(v)
    );
  } catch {
    return [];
  }
}

export function setSubscribedCategories(categories: string[]): void {
  if (typeof window === "undefined") return;
  try {
    const unique = [...new Set(categories)].filter((c) => VALID_IDS.has(c));
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(unique));
  } catch {
    // localStorage 사용 불가 환경(사생활 모드 등)에서는 조용히 무시
  }
}

/* ------------------------------------------------------------------ */
/* 첫 방문(온보딩 완료) 여부                                            */
/* ------------------------------------------------------------------ */

const ONBOARDED_KEY = "notice:onboarded";

/**
 * 온보딩을 마친 적이 있는지. localStorage를 못 쓰는 환경(사생활 모드 등)에서는
 * 온보딩을 반복해서 띄우지 않도록 true(=통과)로 간주합니다.
 */
export function hasOnboarded(): boolean {
  if (typeof window === "undefined") return true;
  try {
    return window.localStorage.getItem(ONBOARDED_KEY) === "1";
  } catch {
    return true;
  }
}

export function markOnboarded(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ONBOARDED_KEY, "1");
  } catch {
    // 조용히 무시
  }
}
