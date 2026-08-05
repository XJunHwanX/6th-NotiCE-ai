import { AlarmClock } from "lucide-react";

import { getDeadlineBadge } from "@/lib/deadline";
import { cn } from "@/lib/utils";

/**
 * Red urgency badge for a notice deadline.
 * Renders nothing when there is no deadline, it has passed, or it is 8+ days away.
 */
export function DeadlineBadge({
  deadline,
  className,
}: {
  deadline: Date | null;
  className?: string;
}) {
  const badge = getDeadlineBadge(deadline);
  if (badge.kind === "none") return null;

  const label = badge.kind === "today" ? "오늘 마감" : `D-${badge.days}`;

  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1 rounded-full bg-red-50 px-2.5 py-1 text-xs font-bold text-red-600",
        className
      )}
    >
      <AlarmClock className="h-3.5 w-3.5" strokeWidth={2.5} />
      {label}
    </span>
  );
}
