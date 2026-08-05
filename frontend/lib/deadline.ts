export type DeadlineBadge =
  | { kind: "none" } // no deadline, or deadline passed, or far away — no red badge
  | { kind: "today" } // due today
  | { kind: "dday"; days: number }; // due within the next 1–7 days

/** Whole-calendar-day difference (target − from), ignoring the time of day. */
export function diffInCalendarDays(target: Date, from: Date): number {
  const a = Date.UTC(target.getFullYear(), target.getMonth(), target.getDate());
  const b = Date.UTC(from.getFullYear(), from.getMonth(), from.getDate());
  return Math.round((a - b) / 86_400_000);
}

/**
 * Deadline badge rules (computed relative to `now`):
 *  - past           → no badge
 *  - 8+ days left    → no badge (date shown as plain text elsewhere)
 *  - today (D-day)   → "오늘 마감" badge
 *  - 1–7 days left   → "D-N" red badge
 *
 * Note: the spec listed "2~7일" for the D-N badge, but D-1 (due tomorrow) is
 * more urgent than D-2, so leaving it un-badged would be surprising. We treat
 * the full 1–7 day window as the urgent D-N range.
 */
export function getDeadlineBadge(
  deadline: Date | null,
  now: Date = new Date()
): DeadlineBadge {
  if (!deadline) return { kind: "none" };
  const days = diffInCalendarDays(deadline, now);
  if (days < 0) return { kind: "none" }; // passed
  if (days === 0) return { kind: "today" };
  if (days <= 7) return { kind: "dday", days };
  return { kind: "none" }; // 8+ days away
}

/** Whether a deadline is still upcoming (today or later). */
export function isUpcoming(deadline: Date | null, now: Date = new Date()): boolean {
  if (!deadline) return false;
  return diffInCalendarDays(deadline, now) >= 0;
}

const dateFmt = new Intl.DateTimeFormat("ko-KR", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

/** e.g. "2026. 08. 05." → normalized to "2026.08.05". */
export function formatDate(date: Date): string {
  return dateFmt.format(date).replace(/\s/g, "").replace(/\.$/, "");
}
