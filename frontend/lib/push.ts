/**
 * 웹 푸시 구독 유틸 (클라이언트 전용).
 * 로그인이 없는 서비스라 브라우저의 PushSubscription 자체가 익명 사용자 식별자가 됩니다.
 */

import { getSupabase, isSupabaseConfigured } from "./supabase";

const VAPID_PUBLIC_KEY = process.env.NEXT_PUBLIC_VAPID_PUBLIC_KEY;

export type SubscribeResult =
  | { ok: true; subscription: PushSubscription }
  | {
      ok: false;
      reason: "unsupported" | "denied" | "not-configured" | "error";
      message: string;
    };

/** 이 브라우저가 서비스워커 + 웹 푸시 + 알림을 지원하는지. */
export function isPushSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "PushManager" in window &&
    "Notification" in window
  );
}

/** base64url(VAPID 공개키) → applicationServerKey 용 Uint8Array. */
function urlBase64ToUint8Array(base64String: string): Uint8Array<ArrayBuffer> {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const output = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i += 1) {
    output[i] = raw.charCodeAt(i);
  }
  return output;
}

/** /sw.js 서비스워커 등록 (이미 등록돼 있으면 기존 등록 반환). */
export function registerServiceWorker(): Promise<ServiceWorkerRegistration> {
  return navigator.serviceWorker.register("/sw.js");
}

/**
 * 생성된 구독을 Supabase `push_subscriptions` 테이블에 endpoint 기준으로 upsert합니다.
 *
 * 팀 합의(backend/README.md): 로그인이 없는 프론트는 별도 API 대신 anon 키로
 * Supabase에 직접 저장합니다. 프론트가 넘기는 영문 카테고리 ID(`academic` 등)는
 * DB 트리거가 파이프라인의 한글 카테고리로 자동 변환하고, 빈 배열이면 enabled를
 * false로 내립니다.
 *
 * Supabase 환경변수가 없는 로컬(더미 모드)에서는 저장을 생략하고 콘솔에만 남깁니다.
 */
async function sendSubscriptionToServer(
  subscription: PushSubscription,
  categories: string[]
): Promise<void> {
  const json = subscription.toJSON();

  if (!isSupabaseConfigured()) {
    console.log(
      "[push] Supabase 미설정 — 구독 저장을 건너뜁니다:",
      JSON.stringify(json, null, 2),
      categories
    );
    return;
  }

  const { error } = await getSupabase()
    .from("push_subscriptions")
    .upsert(
      {
        endpoint: json.endpoint,
        p256dh: json.keys?.p256dh,
        auth: json.keys?.auth,
        categories,
        enabled: categories.length > 0,
      },
      { onConflict: "endpoint" }
    );

  if (error) {
    throw new Error(`구독 저장에 실패했어요: ${error.message}`);
  }
}

/**
 * 알림 권한을 요청하고 푸시 구독을 생성합니다.
 * 성공하면 구독 객체를 (지금은 콘솔로) 서버 전송 자리까지 넘깁니다.
 */
export async function subscribeToPush(
  categories: string[] = []
): Promise<SubscribeResult> {
  if (!isPushSupported()) {
    return {
      ok: false,
      reason: "unsupported",
      message: "이 브라우저는 웹 푸시를 지원하지 않아요.",
    };
  }

  if (!VAPID_PUBLIC_KEY) {
    return {
      ok: false,
      reason: "not-configured",
      message: "푸시 설정(VAPID 키)이 아직 준비되지 않았어요.",
    };
  }

  try {
    // 권한 요청은 사용자 제스처 직후에 하는 게 안전하므로 서비스워커 등록보다 먼저 호출.
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      return {
        ok: false,
        reason: "denied",
        message: "알림 권한이 허용되지 않았어요.",
      };
    }

    const registration = await registerServiceWorker();
    await navigator.serviceWorker.ready;

    // 이미 구독돼 있으면 재사용
    let subscription = await registration.pushManager.getSubscription();
    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(VAPID_PUBLIC_KEY),
      });
    }

    await sendSubscriptionToServer(subscription, categories);
    return { ok: true, subscription };
  } catch (err) {
    return {
      ok: false,
      reason: "error",
      message: (err as Error)?.message || "알림 설정 중 오류가 발생했어요.",
    };
  }
}

export type DisableResult =
  | { ok: true }
  | { ok: false; reason: "unsupported" | "error"; message: string };

/**
 * 알림 "발송만 중단"합니다. 브라우저 구독(PushSubscription)은 그대로 두고
 * Supabase의 enabled 플래그만 false로 내려 발송 대상에서 제외합니다.
 * 다시 켜면 subscribeToPush로 복구됩니다.
 */
export async function disablePush(): Promise<DisableResult> {
  if (!isPushSupported()) {
    return {
      ok: false,
      reason: "unsupported",
      message: "이 브라우저는 웹 푸시를 지원하지 않아요.",
    };
  }

  // Supabase 미설정(더미) 환경에서는 저장할 곳이 없으므로 로컬 상태만 유지.
  if (!isSupabaseConfigured()) return { ok: true };

  try {
    const registration = await navigator.serviceWorker.getRegistration();
    const subscription = registration
      ? await registration.pushManager.getSubscription()
      : null;

    // 구독이 없으면 끌 것도 없음.
    if (!subscription) return { ok: true };

    const { error } = await getSupabase()
      .from("push_subscriptions")
      .update({ enabled: false })
      .eq("endpoint", subscription.endpoint);

    if (error) {
      return {
        ok: false,
        reason: "error",
        message: `알림 끄기에 실패했어요: ${error.message}`,
      };
    }
    return { ok: true };
  } catch (err) {
    return {
      ok: false,
      reason: "error",
      message: (err as Error)?.message || "알림 끄기 중 오류가 발생했어요.",
    };
  }
}
