"use client";

import * as React from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ChevronLeft, Bell, BellOff, BellRing, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { CategoryTag } from "@/components/category-tag";
import { CATEGORIES, type CategoryId } from "@/lib/categories";
import { isPushSupported, subscribeToPush } from "@/lib/push";
import {
  getSubscribedCategories,
  setSubscribedCategories,
} from "@/lib/subscription-store";

type PermissionState = NotificationPermission | "unsupported";

export default function SettingsPage() {
  const [selected, setSelected] = React.useState<Set<CategoryId>>(new Set());
  const [permission, setPermission] = React.useState<PermissionState | null>(
    null
  );
  const [mounted, setMounted] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [saved, setSaved] = React.useState(false);

  // localStorage / Notification 은 클라이언트에서만 접근 → 마운트 후 로드
  React.useEffect(() => {
    setSelected(new Set(getSubscribedCategories()));
    setPermission(isPushSupported() ? Notification.permission : "unsupported");
    setMounted(true);
  }, []);

  const toggle = (id: CategoryId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setSaved(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setSubscribedCategories([...selected]);
    // 권한 요청 + 구독 갱신(서버 전송 자리). 이미 허용된 경우 프롬프트 없이 통과.
    await subscribeToPush([...selected]);
    if (isPushSupported()) setPermission(Notification.permission);
    setSaving(false);
    setSaved(true);
  };

  const enableNotifications = async () => {
    const result = await subscribeToPush([...selected]);
    if (isPushSupported()) setPermission(Notification.permission);
    if (result.ok) setSaved(true);
  };

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background">
      {/* Header */}
      <header className="sticky top-0 z-20 flex items-center gap-1 border-b border-border bg-background/90 px-2 py-2.5 backdrop-blur">
        <Link
          href="/"
          aria-label="홈으로"
          className="flex h-10 w-10 items-center justify-center rounded-md text-foreground transition-colors hover:bg-secondary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <ChevronLeft className="h-5 w-5" />
        </Link>
        <span className="text-sm font-semibold text-foreground">알림 설정</span>
      </header>

      <main className="flex-1 px-5 py-5">
        {/* Permission banner */}
        <PermissionBanner
          permission={mounted ? permission : null}
          onEnable={enableNotifications}
        />

        {/* Category toggles */}
        <h2 className="mb-1 mt-7 px-1 text-sm font-bold text-foreground">
          알림 받을 카테고리
        </h2>
        <p className="mb-3 px-1 text-xs text-muted-foreground">
          켜둔 카테고리의 새 공지만 알림으로 받아요.
        </p>

        <div className="divide-y divide-border overflow-hidden rounded-xl border border-border">
          {CATEGORIES.map((cat) => {
            const on = selected.has(cat.id);
            return (
              <label
                key={cat.id}
                className="flex cursor-pointer items-center justify-between gap-3 px-4 py-3.5 transition-colors hover:bg-muted/50"
              >
                <span className="flex items-center gap-2.5">
                  <CategoryTag category={cat.id} />
                  <span className="text-sm text-muted-foreground">
                    {cat.desc}
                  </span>
                </span>
                <Switch
                  checked={on}
                  onCheckedChange={() => toggle(cat.id)}
                  aria-label={`${cat.label} 알림`}
                />
              </label>
            );
          })}
        </div>

        {/* Save */}
        <div className="mt-6">
          <Button
            size="lg"
            className="w-full"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "저장 중…" : "저장하기"}
          </Button>

          <div className="mt-3 flex h-5 items-center justify-center">
            <AnimatePresence>
              {saved && (
                <motion.p
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="flex items-center gap-1 text-sm font-medium text-primary"
                >
                  <Check className="h-4 w-4" strokeWidth={3} />
                  {selected.size > 0
                    ? "알림 설정이 저장되었어요"
                    : "모든 알림을 껐어요"}
                </motion.p>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Permission banner                                                   */
/* ------------------------------------------------------------------ */

function PermissionBanner({
  permission,
  onEnable,
}: {
  permission: PermissionState | null;
  onEnable: () => void;
}) {
  // 마운트 전(권한 미확정): 레이아웃 유지를 위한 플레이스홀더
  if (permission === null) {
    return <div className="h-[68px] rounded-xl bg-muted" aria-hidden />;
  }

  if (permission === "granted") {
    return (
      <div className="flex items-start gap-3 rounded-xl bg-accent p-4">
        <Bell className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
        <div>
          <p className="text-sm font-semibold text-accent-foreground">
            알림이 허용되어 있어요
          </p>
          <p className="text-xs text-accent-foreground/80">
            새 공지 알림을 바로 받아볼 수 있어요
          </p>
        </div>
      </div>
    );
  }

  if (permission === "denied") {
    return (
      <div className="flex items-start gap-3 rounded-xl bg-amber-50 p-4">
        <BellOff className="mt-0.5 h-5 w-5 shrink-0 text-amber-600" />
        <div>
          <p className="text-sm font-semibold text-amber-800">
            알림이 차단되어 있어요
          </p>
          <p className="text-xs text-amber-700/80">
            브라우저 주소창의 🔒 → 사이트 설정에서 알림을 허용해 주세요.
          </p>
        </div>
      </div>
    );
  }

  if (permission === "unsupported") {
    return (
      <div className="flex items-start gap-3 rounded-xl bg-muted p-4">
        <BellOff className="mt-0.5 h-5 w-5 shrink-0 text-muted-foreground" />
        <div>
          <p className="text-sm font-semibold text-foreground">
            이 브라우저는 웹 푸시를 지원하지 않아요
          </p>
          <p className="text-xs text-muted-foreground">
            설정은 저장되며, 지원 브라우저에서 알림을 받을 수 있어요.
          </p>
        </div>
      </div>
    );
  }

  // "default" — 아직 권한 요청 전
  return (
    <div className="flex items-center gap-3 rounded-xl bg-accent p-4">
      <BellRing className="h-5 w-5 shrink-0 text-primary" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-semibold text-accent-foreground">
          알림이 아직 꺼져 있어요
        </p>
        <p className="text-xs text-accent-foreground/80">
          알림을 켜면 새 공지를 바로 받아볼 수 있어요
        </p>
      </div>
      <Button size="sm" onClick={onEnable} className="shrink-0">
        켜기
      </Button>
    </div>
  );
}
