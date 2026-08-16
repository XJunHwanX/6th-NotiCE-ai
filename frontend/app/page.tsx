import { AlertCircle } from "lucide-react";

import { getNotices } from "@/lib/notices";
import { HomeClient } from "@/components/home-client";
import { OnboardingGate } from "@/components/onboarding-gate";

// 캐시된 목록(ISR)을 CDN에서 즉시 보여 이동을 빠르게 하고, 최신성은 HomeClient가
// 마운트 시 브라우저에서 다시 조회해 보완한다(알림으로 온 새 공지도 곧 목록에 반영됨).
export const revalidate = 600; // 즉시 표시용 baseline; 실시간성은 클라 재조회가 담당

export default async function HomePage() {
  let notices;
  try {
    notices = await getNotices();
  } catch (err) {
    return <LoadError message={(err as Error).message} />;
  }

  return (
    <>
      <OnboardingGate />
      <HomeClient notices={notices} />
    </>
  );
}

function LoadError({ message }: { message: string }) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col items-center justify-center gap-3 bg-background px-6 text-center">
      <div className="flex h-14 w-14 items-center justify-center rounded-full bg-red-50 text-red-600">
        <AlertCircle className="h-7 w-7" />
      </div>
      <h1 className="text-lg font-bold text-foreground">
        공지를 불러오지 못했어요
      </h1>
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
