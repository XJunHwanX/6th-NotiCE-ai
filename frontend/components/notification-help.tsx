"use client";

import * as React from "react";
import { BellRing, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

type Platform = "ios" | "ios-installed" | "android" | "other";

/**
 * 접고 펼 수 있는 "알림 받는 방법" 안내.
 * 플랫폼에 맞춰 내용을 보여줍니다.
 * - iOS(미설치): 홈 화면에 추가해야 알림을 받을 수 있음(Apple 정책)
 * - iOS(설치됨): 아래에서 알림만 켜면 됨
 * - Android / 데스크톱: 따로 설치할 필요 없이 알림만 허용하면 됨
 * 설정을 마친 뒤에도 항상 보이며, 접힌 상태로 두었다가 필요할 때 다시 펼 수 있습니다.
 */
export function NotificationHelp() {
  const [platform, setPlatform] = React.useState<Platform | null>(null);
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    const ua = navigator.userAgent.toLowerCase();
    const isIOS =
      /iphone|ipad|ipod/.test(ua) ||
      (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    const isAndroid = /android/.test(ua);
    const standalone =
      window.matchMedia("(display-mode: standalone)").matches ||
      (window.navigator as unknown as { standalone?: boolean }).standalone ===
        true;

    let p: Platform;
    if (isIOS) p = standalone ? "ios-installed" : "ios";
    else if (isAndroid) p = "android";
    else p = "other";

    setPlatform(p);
    // 홈 화면 추가가 꼭 필요한 iOS 미설치 사용자는 처음엔 펼쳐서 안내
    if (p === "ios") setOpen(true);
  }, []);

  return (
    <div className="mb-4 overflow-hidden rounded-xl border border-border">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center justify-between gap-2 bg-muted/40 px-4 py-3 text-left transition-colors hover:bg-muted/70"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-foreground">
          <BellRing className="h-4 w-4 shrink-0 text-primary" />
          알림 받는 방법
        </span>
        <ChevronDown
          className={cn(
            "h-4 w-4 shrink-0 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div className="border-t border-border px-4 py-3.5 text-xs leading-relaxed text-muted-foreground">
          {platform === "ios" && <IosGuide />}
          {platform === "ios-installed" && (
            <p>
              앱 설치가 완료됐어요. 아래{" "}
              <span className="font-medium text-foreground">알림 받기</span>를
              켜고 알림을 허용하면 새 공지를 알림으로 받을 수 있어요.
            </p>
          )}
          {platform === "android" && (
            <div className="space-y-1.5">
              <p>
                <span className="font-medium text-foreground">
                  안드로이드는 따로 설치할 필요가 없어요.
                </span>{" "}
                아래 <span className="font-medium text-foreground">알림 받기</span>
                를 켜고 알림을 허용하면 바로 받을 수 있어요.
              </p>
              <p>
                더 앱처럼 쓰고 싶다면 Chrome 메뉴(⋮)의{" "}
                <span className="font-medium text-foreground">홈 화면에 추가</span>
                를 눌러 설치할 수도 있어요. (선택)
              </p>
            </div>
          )}
          {platform === "other" && (
            <p>
              이 브라우저는 따로 설치할 필요 없이, 아래{" "}
              <span className="font-medium text-foreground">알림 받기</span>를
              켜고 알림을 허용하면 바로 받을 수 있어요. (Chrome·Edge 등 데스크톱
              브라우저 지원)
            </p>
          )}
          {platform === null && <p>알림 설정 방법을 불러오는 중이에요…</p>}
        </div>
      )}
    </div>
  );
}

function IosGuide() {
  return (
    <div className="space-y-1.5">
      <p>
        iPhone은{" "}
        <span className="font-medium text-foreground">
          Safari로 홈 화면에 추가한 앱
        </span>
        에서만 알림을 받을 수 있어요 (Apple 정책). 아래 순서로 추가해 주세요.
      </p>
      <ol className="space-y-1 text-accent-foreground/90">
        <li>
          1. Safari 하단(또는 상단)의{" "}
          <span className="font-medium text-foreground">공유 버튼</span>을 탭
        </li>
        <li>
          2. 목록에서{" "}
          <span className="font-medium text-foreground">홈 화면에 추가</span>를
          선택
        </li>
        <li>
          3. 홈 화면의 <span className="font-medium text-foreground">NotiCE</span>{" "}
          앱을 열고, 아래{" "}
          <span className="font-medium text-foreground">알림 받기</span>를 켜기
        </li>
      </ol>
    </div>
  );
}
