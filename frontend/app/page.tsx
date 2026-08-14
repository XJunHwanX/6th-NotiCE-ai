import { AlertCircle } from "lucide-react";

import { getNotices } from "@/lib/notices";
import { HomeClient } from "@/components/home-client";
import { OnboardingGate } from "@/components/onboarding-gate";

// 알림을 눌러 홈으로 들어온 사용자에게 방금 뜬 공지가 항상 보이도록 매 방문 최신 조회한다.
// 조회 지연은 loading.tsx 스켈레톤으로 즉시 가려, 이동은 즉각적으로 느껴진다.
export const dynamic = "force-dynamic";

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
