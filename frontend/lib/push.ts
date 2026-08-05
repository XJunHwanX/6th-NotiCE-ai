/**
 * 웹 푸시 구독 유틸 (클라이언트 전용).
 * 로그인이 없는 서비스라 브라우저의 PushSubscription 자체가 익명 사용자 식별자가 됩니다.
 */

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
 * 생성된 구독 객체를 서버에 저장하는 자리.
 * TODO(backend): 구독 저장 엔드포인트가 준비되면 아래 fetch 주석을 실제 URL로 교체.
 *
 *   await fetch("/api/subscriptions", {
 *     method: "POST",
 *     headers: { "Content-Type": "application/json" },
 *     body: JSON.stringify({ subscription: subscription.toJSON(), categories }),
 *   });
 *
 * 지금은 백엔드 미구현 상태라 콘솔에 구독 객체만 출력합니다.
 */
async function sendSubscriptionToServer(
  subscription: PushSubscription,
  categories: string[]
): Promise<void> {
  console.log(
    "[push] 구독 객체 (서버 전송 예정):",
    JSON.stringify(subscription.toJSON(), null, 2)
  );
  console.log("[push] 구독 카테고리:", categories);
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
