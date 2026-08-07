import { ExternalLink } from "lucide-react";

import { Card } from "@/components/ui/card";
import { CategoryTag } from "@/components/category-tag";
import { DeadlineBadge } from "@/components/deadline-badge";
import { formatDate } from "@/lib/deadline";
import { type Notice } from "@/lib/notices";

const MAX_TAGS = 2;

export function NoticeCard({ notice }: { notice: Notice }) {
  const shown = notice.categories.slice(0, MAX_TAGS);
  const extra = notice.categories.length - shown.length;

  return (
    <a
      href={notice.url}
      target="_blank"
      rel="noopener noreferrer"
      className="block rounded-xl focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <Card className="group p-4 transition-all hover:border-primary/40 hover:shadow-md active:scale-[0.99]">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div className="flex min-w-0 flex-wrap items-center gap-1.5">
            {shown.map((c) => (
              <CategoryTag key={c} category={c} />
            ))}
            {extra > 0 && (
              <span className="text-xs font-medium text-muted-foreground">
                +{extra}
              </span>
            )}
          </div>
          <DeadlineBadge deadline={notice.deadline} />
        </div>

        <h3 className="line-clamp-2 text-[15px] font-semibold leading-snug tracking-tight text-foreground transition-colors group-hover:text-primary">
          {notice.title}
        </h3>

        <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
          {notice.publishedAt && <span>게시 {formatDate(notice.publishedAt)}</span>}
          {notice.deadline && (
            <>
              {notice.publishedAt && <span aria-hidden>·</span>}
              <span>마감 {formatDate(notice.deadline)}</span>
            </>
          )}
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-muted-foreground/70 transition-colors group-hover:text-primary">
            원문
            <ExternalLink className="h-3 w-3" />
          </span>
        </div>
      </Card>
    </a>
  );
}
