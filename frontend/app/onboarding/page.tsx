"use client";

import * as React from "react";
import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import {
  BookOpen,
  GraduationCap,
  Microscope,
  Users,
  Wallet,
  Trophy,
  Briefcase,
  MoreHorizontal,
  Bell,
  BellRing,
  Check,
  ChevronLeft,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { subscribeToPush } from "@/lib/push";
import {
  markOnboarded,
  setSubscribedCategories,
} from "@/lib/subscription-store";

/* ------------------------------------------------------------------ */
/* Data                                                                */
/* ------------------------------------------------------------------ */

type Category = {
  id: string;
  label: string;
  desc: string;
  icon: LucideIcon;
};

const CATEGORIES: Category[] = [
  { id: "academic", label: "학사", desc: "수강신청·시험·성적", icon: BookOpen },
  { id: "graduation", label: "졸업", desc: "졸업요건·논문", icon: GraduationCap },
  { id: "research", label: "대학원/연구", desc: "연구실·세미나", icon: Microscope },
  { id: "activity", label: "학생활동", desc: "동아리·행사", icon: Users },
  { id: "scholarship", label: "장학/근로", desc: "장학금·교내근로", icon: Wallet },
  { id: "contest", label: "대회/공모전", desc: "해커톤·경진대회", icon: Trophy },
  { id: "career", label: "취업/인턴", desc: "채용·인턴십", icon: Briefcase },
  { id: "etc", label: "기타", desc: "그 외 공지", icon: MoreHorizontal },
];

const TOTAL_STEPS = 3;

/* ------------------------------------------------------------------ */
/* Animation variants                                                  */
/* ------------------------------------------------------------------ */

const stepVariants = {
  enter: (dir: number) => ({
    x: dir > 0 ? 48 : -48,
    opacity: 0,
  }),
  center: { x: 0, opacity: 1 },
  exit: (dir: number) => ({
    x: dir > 0 ? -48 : 48,
    opacity: 0,
  }),
};

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function OnboardingPage() {
  const [[step, direction], setStep] = React.useState<[number, number]>([1, 0]);
  const [selected, setSelected] = React.useState<Set<string>>(new Set());
  const [permission, setPermission] =
    React.useState<NotificationPermission | "unsupported" | "error" | null>(
      null
    );
  const [done, setDone] = React.useState(false);

  const paginate = (next: number) =>
    setStep(([cur]) => [next, next > cur ? 1 : -1]);

  const toggleCategory = (id: string) => {
    setSelected((prev) => {
      const nextSet = new Set(prev);
      if (nextSet.has(id)) nextSet.delete(id);
      else nextSet.add(id);
      return nextSet;
    });
  };

  const requestPermission = async () => {
    // 고른 카테고리를 로컬에 저장 (설정 화면에서 다시 불러와 편집 가능)
    setSubscribedCategories([...selected]);
    markOnboarded();
    const result = await subscribeToPush([...selected]);
    if (result.ok) {
      setPermission("granted");
    } else if (result.reason === "denied") {
      setPermission("denied");
    } else if (result.reason === "unsupported") {
      setPermission("unsupported");
    } else {
      // "not-configured" | "error"
      setPermission("error");
    }
    setDone(true);
  };

  const skipPermission = () => {
    setSubscribedCategories([...selected]);
    markOnboarded();
    setPermission(null);
    setDone(true);
  };

  return (
    <div className="flex min-h-dvh w-full flex-col items-center justify-center bg-muted px-4 py-8">
      <div className="w-full max-w-md">
        {/* Brand */}
        <div className="mb-6 flex items-center justify-center gap-2">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <Bell className="h-5 w-5" />
          </div>
          <span className="text-lg font-bold tracking-tight text-foreground">
            NotiCE
          </span>
        </div>

        {/* Progress */}
        {!done && (
          <div className="mb-5 flex items-center gap-2 px-1">
            {Array.from({ length: TOTAL_STEPS }).map((_, i) => (
              <div
                key={i}
                className="h-1.5 flex-1 overflow-hidden rounded-full bg-border"
              >
                <motion.div
                  className="h-full rounded-full bg-primary"
                  initial={false}
                  animate={{ width: i < step ? "100%" : "0%" }}
                  transition={{ duration: 0.35, ease: "easeInOut" }}
                />
              </div>
            ))}
          </div>
        )}

        <Card className="overflow-hidden">
          <AnimatePresence mode="wait" custom={direction}>
            {done ? (
              <motion.div
                key="done"
                initial={{ opacity: 0, scale: 0.96 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ duration: 0.3, ease: "easeOut" }}
              >
                <DoneStep
                  permission={permission}
                  selectedCount={selected.size}
                />
              </motion.div>
            ) : (
              <motion.div
                key={step}
                custom={direction}
                variants={stepVariants}
                initial="enter"
                animate="center"
                exit="exit"
                transition={{
                  x: { type: "spring", stiffness: 320, damping: 32 },
                  opacity: { duration: 0.2 },
                }}
              >
                {step === 1 && <IntroStep />}
                {step === 2 && (
                  <CategoryStep
                    selected={selected}
                    onToggle={toggleCategory}
                  />
                )}
                {step === 3 && (
                  <PermissionStep
                    onAllow={requestPermission}
                    onSkip={skipPermission}
                  />
                )}
              </motion.div>
            )}
          </AnimatePresence>

          {/* Footer nav */}
          {!done && (
            <div className="flex items-center gap-3 border-t border-border bg-muted/40 px-6 py-4">
              {step > 1 ? (
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => paginate(step - 1)}
                  aria-label="이전"
                >
                  <ChevronLeft className="h-5 w-5" />
                </Button>
              ) : (
                <div className="h-10 w-10" />
              )}

              <div className="flex-1" />

              {step < 3 && (
                <Button
                  onClick={() => paginate(step + 1)}
                  disabled={step === 2 && selected.size === 0}
                  className="min-w-[7rem]"
                >
                  {step === 2
                    ? `다음${selected.size ? ` (${selected.size})` : ""}`
                    : "시작하기"}
                </Button>
              )}
            </div>
          )}
        </Card>

        {!done && step === 2 && (
          <p className="mt-3 text-center text-xs text-muted-foreground">
            나중에 설정에서 언제든지 바꿀 수 있어요.
          </p>
        )}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Step 1 — Intro                                                      */
/* ------------------------------------------------------------------ */

function IntroStep() {
  const features = [
    {
      icon: Sparkles,
      title: "카테고리별 맞춤 구독",
      desc: "관심 있는 공지만 골라서 받아보세요.",
    },
    {
      icon: BellRing,
      title: "실시간 웹 푸시 알림",
      desc: "새 공지가 올라오면 바로 알려드려요.",
    },
    {
      icon: ShieldCheck,
      title: "이제 공지 놓칠 일 없어요",
      desc: "학과 홈페이지를 매번 확인할 필요 없이.",
    },
  ];

  return (
    <>
      <CardHeader className="items-center pt-8 text-center">
        <motion.div
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 18 }}
          className="mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent"
        >
          <Bell className="h-8 w-8 text-primary" />
        </motion.div>
        <CardTitle className="text-2xl">
          공지, 이제 알림으로 받으세요
        </CardTitle>
        <CardDescription className="mt-1 text-base leading-relaxed">
          홍익대 컴퓨터공학과 공지사항을
          <br />
          카테고리별로 구독하고 알림을 받는 서비스예요.
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-8">
        <ul className="space-y-4">
          {features.map((f, i) => (
            <motion.li
              key={f.title}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.15 + i * 0.1, duration: 0.35 }}
              className="flex items-start gap-3"
            >
              <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
                <f.icon className="h-5 w-5" />
              </div>
              <div>
                <p className="text-sm font-semibold text-foreground">
                  {f.title}
                </p>
                <p className="text-sm text-muted-foreground">{f.desc}</p>
              </div>
            </motion.li>
          ))}
        </ul>
      </CardContent>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Step 2 — Category chips                                             */
/* ------------------------------------------------------------------ */

function CategoryStep({
  selected,
  onToggle,
}: {
  selected: Set<string>;
  onToggle: (id: string) => void;
}) {
  return (
    <>
      <CardHeader className="pt-8">
        <CardTitle className="text-2xl">관심 카테고리 선택</CardTitle>
        <CardDescription className="text-base">
          구독할 공지 카테고리를 골라주세요. (복수 선택 가능)
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-8">
        <div className="flex flex-wrap gap-2.5">
          {CATEGORIES.map((cat) => {
            const active = selected.has(cat.id);
            const Icon = cat.icon;
            return (
              <motion.button
                key={cat.id}
                type="button"
                onClick={() => onToggle(cat.id)}
                whileTap={{ scale: 0.94 }}
                aria-pressed={active}
                className={cn(
                  "group flex items-center gap-2 rounded-full border px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                  active
                    ? "border-primary bg-primary text-primary-foreground shadow-sm"
                    : "border-border bg-background text-foreground hover:border-primary/40 hover:bg-accent/60"
                )}
              >
                <Icon
                  className={cn(
                    "h-4 w-4 transition-colors",
                    active ? "text-primary-foreground" : "text-muted-foreground"
                  )}
                />
                {cat.label}
                <AnimatePresence initial={false}>
                  {active && (
                    <motion.span
                      initial={{ width: 0, opacity: 0 }}
                      animate={{ width: "auto", opacity: 1 }}
                      exit={{ width: 0, opacity: 0 }}
                      transition={{ duration: 0.18 }}
                      className="flex items-center overflow-hidden"
                    >
                      <Check className="h-4 w-4" strokeWidth={3} />
                    </motion.span>
                  )}
                </AnimatePresence>
              </motion.button>
            );
          })}
        </div>
      </CardContent>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Step 3 — Push permission                                            */
/* ------------------------------------------------------------------ */

function PermissionStep({
  onAllow,
  onSkip,
}: {
  onAllow: () => void;
  onSkip: () => void;
}) {
  return (
    <>
      <CardHeader className="items-center pt-8 text-center">
        <motion.div
          initial={{ scale: 0.7, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 260, damping: 18 }}
          className="relative mb-3 flex h-16 w-16 items-center justify-center rounded-2xl bg-accent"
        >
          <BellRing className="h-8 w-8 text-primary" />
          <motion.span
            className="absolute right-3 top-3 h-2.5 w-2.5 rounded-full bg-primary"
            animate={{ scale: [1, 1.5, 1], opacity: [1, 0.4, 1] }}
            transition={{ repeat: Infinity, duration: 1.6, ease: "easeInOut" }}
          />
        </motion.div>
        <CardTitle className="text-2xl">알림을 켜주세요</CardTitle>
        <CardDescription className="mt-1 text-base leading-relaxed">
          새로운 공지가 등록되면 웹 푸시 알림으로
          <br />
          가장 먼저 알려드릴게요.
        </CardDescription>
      </CardHeader>
      <CardContent className="pb-8">
        <div className="mb-6 flex items-start gap-3 rounded-xl bg-muted p-4">
          <ShieldCheck className="mt-0.5 h-5 w-5 shrink-0 text-primary" />
          <p className="text-sm text-muted-foreground">
            알림은 선택한 카테고리의 공지에만 사용되며, 언제든지 브라우저 설정에서
            끌 수 있어요.
          </p>
        </div>
        <div className="flex flex-col gap-2.5">
          <Button size="lg" onClick={onAllow}>
            <BellRing className="h-5 w-5" />
            알림 허용하기
          </Button>
          <Button variant="ghost" onClick={onSkip}>
            나중에 할게요
          </Button>
        </div>
      </CardContent>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* Done                                                                */
/* ------------------------------------------------------------------ */

function DoneStep({
  permission,
  selectedCount,
}: {
  permission: NotificationPermission | "unsupported" | "error" | null;
  selectedCount: number;
}) {
  const granted = permission === "granted";
  const message = granted
    ? "알림이 켜졌어요. 새 공지를 놓치지 않도록 바로 알려드릴게요!"
    : permission === "denied"
    ? "알림 권한이 꺼져 있어요. 브라우저 설정에서 언제든 켤 수 있어요."
    : permission === "unsupported"
    ? "이 브라우저는 웹 푸시를 지원하지 않지만, 구독 설정은 저장됐어요."
    : permission === "error"
    ? "알림 설정 중 문제가 생겼어요. 나중에 설정에서 다시 켤 수 있어요."
    : "설정이 저장됐어요. 알림은 나중에 켤 수 있어요.";

  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <motion.div
        initial={{ scale: 0 }}
        animate={{ scale: 1 }}
        transition={{ type: "spring", stiffness: 260, damping: 16, delay: 0.05 }}
        className={cn(
          "mb-5 flex h-20 w-20 items-center justify-center rounded-full",
          granted ? "bg-primary" : "bg-accent"
        )}
      >
        <Check
          className={cn(
            "h-10 w-10",
            granted ? "text-primary-foreground" : "text-primary"
          )}
          strokeWidth={3}
        />
      </motion.div>
      <h2 className="text-2xl font-bold text-foreground">준비 완료!</h2>
      <p className="mt-2 max-w-xs text-base leading-relaxed text-muted-foreground">
        {message}
      </p>
      <div className="mt-6 w-full rounded-xl bg-muted p-4 text-sm">
        <span className="text-muted-foreground">구독한 카테고리 </span>
        <span className="font-semibold text-foreground">
          {selectedCount}개
        </span>
      </div>
      <Button asChild size="lg" className="mt-6 w-full">
        <Link href="/">공지 보러가기</Link>
      </Button>
    </div>
  );
}
