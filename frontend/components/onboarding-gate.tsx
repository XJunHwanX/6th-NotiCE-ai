"use client";

import * as React from "react";
import { useRouter } from "next/navigation";

import { hasOnboarded } from "@/lib/subscription-store";

/**
 * 첫 방문자를 온보딩(/onboarding)으로 보냅니다.
 * 온보딩을 마치면 localStorage 플래그가 저장되어, 이후 방문에는 홈이 바로 보입니다.
 * 홈 페이지에 마운트되며 클라이언트에서만 판단합니다(서버 렌더에는 영향 없음).
 */
export function OnboardingGate() {
  const router = useRouter();

  React.useEffect(() => {
    if (!hasOnboarded()) {
      router.replace("/onboarding");
    }
  }, [router]);

  return null;
}
