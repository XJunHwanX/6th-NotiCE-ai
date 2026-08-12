"use client";

import * as React from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bell, BellOff, BellRing, Check, CircleAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { CategoryTag } from "@/components/category-tag";
import { TabBar } from "@/components/tab-bar";
import { NotificationHelp } from "@/components/notification-help";
import { cn } from "@/lib/utils";
import { CATEGORIES, type CategoryId } from "@/lib/categories";
import { disablePush, isPushSupported, subscribeToPush } from "@/lib/push";
import {
  getPushEnabledPref,
  getSubscribedCategories,
  setPushEnabledPref,
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
  const [feedback, setFeedback] = React.useState<{
    type: "ok" | "error";
    text: string;
  } | null>(null);
  // 알림 받기 마스터 on/off (끄면 발송만 중단, 구독은 유지)
  const [pushOn, setPushOn] = React.useState(false);

  // localStorage / Notification 은 클라이언트에서만 접근 → 마운트 후 로드
  React.useEffect(() => {
    const cats = getSubscribedCategories();
    const perm = isPushSupported() ? Notification.permission : "unsupported";
    setSelected(new Set(cats));
    setPermission(perm);
    // 저장된 on/off 값이 없으면 이미 구독한 상태(권한 허용 + 카테고리 있음)로 추정
    const pref = getPushEnabledPref();
    setPushOn(pref ?? (perm === "granted" && cats.length > 0));
    setMounted(true);
  }, []);

  const toggle = (id: CategoryId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setFeedback(null);
  };

  const handleSave = async () => {
    setSaving(true);
    setSubscribedCategories([...selected]);

    // 알림이 꺼진 상태면 카테고리만 로컬에 저장하고 발송은 중단 유지.
    if (!pushOn) {
      setSaving(false);
      setFeedback({
        type: "ok",
        text: "카테고리를 저장했어요 (알림은 꺼져 있어요)",
      });
      return;
    }

    // 권한 요청 + 구독을 Supabase에 저장. 이미 허용된 경우 프롬프트 없이 통과.
    const result = await subscribeToPush([...selected]);
    if (isPushSupported()) setPermission(Notification.permission);
    setSaving(false);

    if (result.ok) {
      setFeedback({
        type: "ok",
        text:
          selected.size > 0
            ? "알림 설정이 저장되었어요"
            : "선택한 카테고리가 없어 알림이 오지 않아요",
      });
    } else if (result.reason === "denied") {
      setPushOn(false);
      setPushEnabledPref(false);
      setFeedback({
        type: "error",
        text: "알림 권한이 거부되어 알림을 받을 수 없어요",
      });
    } else if (
      result.reason === "unsupported" ||
      result.reason === "not-configured"
    ) {
      // 이 브라우저/환경은 푸시가 안 되지만 카테고리 설정은 로컬에 저장됨
      setFeedback({ type: "ok", text: "설정을 저장했어요" });
    } else {
      setFeedback({ type: "error", text: result.message });
    }
  };

  // 마스터 "알림 받기" 스위치
  const toggleMaster = async (next: boolean) => {
    setFeedback(null);
    setSaving(true);

    if (next) {
      setSubscribedCategories([...selected]);
      const result = await subscribeToPush([...selected]);
      if (isPushSupported()) setPermission(Notification.permission);
      setSaving(false);

      if (result.ok) {
        setPushOn(true);
        setPushEnabledPref(true);
        setFeedback({ type: "ok", text: "알림을 켰어요" });
      } else if (result.reason === "denied") {
        setPushOn(false);
        setPushEnabledPref(false);
        setFeedback({
          type: "error",
          text: "알림 권한이 거부되어 켤 수 없어요",
        });
      } else if (
        result.reason === "unsupported" ||
        result.reason === "not-configured"
      ) {
        setPushOn(true);
        setPushEnabledPref(true);
        setFeedback({ type: "ok", text: "설정을 저장했어요" });
      } else {
        setPushOn(false);
        setPushEnabledPref(false);
        setFeedback({ type: "error", text: result.message });
      }
      return;
    }

    // 끄기: 구독은 두고 발송만 중단
    setPushOn(false);
    setPushEnabledPref(false);
    const result = await disablePush();
    setSaving(false);
    if (result.ok || result.reason === "unsupported") {
      setFeedback({ type: "ok", text: "알림을 껐어요" });
    } else {
      setFeedback({ type: "error", text: result.message });
    }
  };

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background pb-20">
      {/* Header */}
      <header className="sticky top-0 z-20 flex items-center gap-2 border-b border-border bg-background/90 px-4 py-3 backdrop-blur">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
          <Bell className="h-[18px] w-[18px]" />
        </div>
        <div className="min-w-0">
          <h1 className="text-base font-bold leading-tight tracking-tight text-foreground">
            알림 설정
          </h1>
          <p className="text-[11px] leading-tight text-muted-foreground">
            카테고리별 공지 알림
          </p>
        </div>
      </header>

      <main className="flex-1 px-5 py-5">
        {/* 접고 펴는 플랫폼별 알림 안내 (iOS/안드로이드/데스크톱) */}
        <NotificationHelp />

        {/* 권한이 차단됐거나 미지원일 때만 안내 */}
        {mounted &&
          (permission === "denied" || permission === "unsupported") && (
            <div className="mb-4">
              <PermissionBanner permission={permission} />
            </div>
          )}

        {/* 알림 받기 마스터 스위치 */}
        <div className="flex items-center justify-between gap-3 rounded-xl border border-border bg-card p-4">
          <span className="flex items-center gap-3">
            <span
              className={cn(
                "flex h-9 w-9 items-center justify-center rounded-lg",
                pushOn
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground"
              )}
            >
              {pushOn ? (
                <BellRing className="h-[18px] w-[18px]" />
              ) : (
                <BellOff className="h-[18px] w-[18px]" />
              )}
            </span>
            <span>
              <span className="block text-sm font-semibold text-foreground">
                알림 받기
              </span>
              <span className="block text-xs text-muted-foreground">
                {pushOn ? "새 공지 알림을 받고 있어요" : "알림이 꺼져 있어요"}
              </span>
            </span>
          </span>
          <Switch
            checked={pushOn}
            onCheckedChange={toggleMaster}
            disabled={saving || permission === "unsupported"}
            aria-label="알림 받기"
          />
        </div>

        {/* Category toggles */}
        <h2 className="mb-1 mt-7 px-1 text-sm font-bold text-foreground">
          알림 받을 카테고리
        </h2>
        <p className="mb-3 px-1 text-xs text-muted-foreground">
          {pushOn
            ? "켜둔 카테고리의 새 공지만 알림으로 받아요."
            : "알림을 켜면 카테고리별로 받을 수 있어요."}
        </p>

        <div
          className={cn(
            "divide-y divide-border overflow-hidden rounded-xl border border-border transition-opacity",
            !pushOn && "opacity-50"
          )}
        >
          {CATEGORIES.map((cat) => {
            const on = selected.has(cat.id);
            return (
              <label
                key={cat.id}
                className={cn(
                  "flex items-center justify-between gap-3 px-4 py-3.5 transition-colors",
                  pushOn
                    ? "cursor-pointer hover:bg-muted/50"
                    : "cursor-default"
                )}
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
                  disabled={!pushOn}
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

          <div className="mt-3 flex min-h-5 items-center justify-center">
            <AnimatePresence mode="wait">
              {feedback && (
                <motion.p
                  key={feedback.text}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className={`flex items-center gap-1 text-sm font-medium ${
                    feedback.type === "ok" ? "text-primary" : "text-red-600"
                  }`}
                >
                  {feedback.type === "ok" ? (
                    <Check className="h-4 w-4 shrink-0" strokeWidth={3} />
                  ) : (
                    <CircleAlert className="h-4 w-4 shrink-0" />
                  )}
                  {feedback.text}
                </motion.p>
              )}
            </AnimatePresence>
          </div>
        </div>
      </main>

      <TabBar active="settings" />
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
  onEnable?: () => void;
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
