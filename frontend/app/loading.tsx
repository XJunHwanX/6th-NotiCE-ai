import { TabBar } from "@/components/tab-bar";

/**
 * 홈(공지) 로딩 스켈레톤.
 * force-dynamic 홈은 매 방문 서버에서 공지를 조회하므로, 그 사이 이 스켈레톤을
 * 즉시 보여 "멈춘 느낌" 없이 곧바로 화면이 전환되게 한다. (Next.js loading.tsx 규약)
 */
export default function HomeLoading() {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background pb-20">
      {/* 헤더 (로고 + 필터 칩) */}
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 px-4 pb-3 pt-4 backdrop-blur">
        <div className="flex items-center gap-2">
          <div className="h-8 w-8 animate-pulse rounded-lg bg-muted" />
          <div className="space-y-1.5">
            <div className="h-3 w-16 animate-pulse rounded bg-muted" />
            <div className="h-2.5 w-28 animate-pulse rounded bg-muted" />
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className="h-8 w-16 animate-pulse rounded-full bg-muted"
            />
          ))}
        </div>
      </header>

      {/* 공지 카드 placeholder */}
      <main className="flex-1 space-y-2.5 px-4 py-4">
        <div className="mb-3 h-3 w-12 animate-pulse rounded bg-muted" />
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="space-y-2.5 rounded-xl border border-border p-4"
          >
            <div className="flex gap-2">
              <div className="h-5 w-14 animate-pulse rounded-full bg-muted" />
              <div className="h-5 w-12 animate-pulse rounded-full bg-muted" />
            </div>
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
            <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
            <div className="mt-1 h-3 w-24 animate-pulse rounded bg-muted" />
          </div>
        ))}
      </main>

      <TabBar active="home" />
    </div>
  );
}
