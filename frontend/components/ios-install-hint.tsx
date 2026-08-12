"use client";

import * as React from "react";
import { BellRing } from "lucide-react";

const DISMISS_KEY = "notice:ios-hint-dismissed";

/**
 * iPhone(iOS)에서만, 그리고 아직 홈 화면에 설치(standalone)되지 않았을 때만
 * "홈 화면에 추가해야 알림을 받을 수 있다"는 안내를 보여줍니다.
 * iOS는 설치형 PWA에서만 웹 푸시를 허용하므로(Apple 정책) 필요한 안내입니다.
 */
export function IosInstallHint() {
  const [show, setShow] = React.useState(false);

  React.useEffect(() => {
    try {
      if (window.localStorage.getItem(DISMISS_KEY) === "1") return;
    } catch {
      // localStorage 사용 불가 환경은 무시하고 계속 판단
    }

    const ua = window.navigator.userAgent.toLowerCase();
    // iPadOS 13+ 는 Mac으로 위장하므로 터치 지원 여부로 보완 판단
    const isIOS =
      /iphone|ipad|ipod/.test(ua) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (window.navigator as unknown as { standalone?: boolean }).standalone ===
        true;

    if (isIOS && !standalone) setShow(true);
  }, []);

  const dismiss = () => {
    setShow(false);
    try {
      window.localStorage.setItem(DISMISS_KEY, "1");
    } catch {
      // 무시
    }
  };

  if (!show) return null;

  return (
    <div className="mb-4 rounded-xl border border-primary/20 bg-accent p-4">
      <div className="flex items-start gap-3">
        <BellRing className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold text-accent-foreground">
            iPhone에서 알림을 받으려면
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-accent-foreground/80">
            iPhone은 홈 화면에 추가한 앱에서만 알림을 받을 수 있어요. 아래 순서로
            추가해 주세요.
          </p>
          <ol className="mt-2.5 space-y-1 text-xs leading-relaxed text-accent-foreground/90">
            <li>
              1. Safari 하단(또는 상단)의{" "}
              <span className="font-medium">공유 버튼</span>을 탭
            </li>
            <li>
              2. 목록에서 <span className="font-medium">홈 화면에 추가</span>를
              선택
            </li>
            <li>
              3. 홈 화면의 <span className="font-medium">NotiCE</span> 앱을 열고{" "}
              <span className="font-medium">알림 허용</span>
            </li>
          </ol>
          <button
            type="button"
            onClick={dismiss}
            className="mt-3 text-xs font-medium text-primary hover:underline"
          >
            다시 보지 않기
          </button>
        </div>
      </div>
    </div>
  );
}
