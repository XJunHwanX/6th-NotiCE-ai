import { AlertCircle } from "lucide-react";

import { getNotices } from "@/lib/notices";
import { HomeClient } from "@/components/home-client";
import { OnboardingGate } from "@/components/onboarding-gate";

// 공지는 6시간마다 크롤링 때만 바뀌므로 매 방문 재조회 대신 ISR 캐시로 제공한다.
// 캐시 만료 후 첫 요청이 오면 백그라운드에서 한 번만 갱신(stale-while-revalidate)하므로
// 탭 이동이 즉각적이고 서버/DB 부하도 낮다.
export const revalidate = 600; // 10분

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
