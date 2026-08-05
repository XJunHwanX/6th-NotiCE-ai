"use client";

import * as React from "react";
import { AnimatePresence, motion } from "motion/react";
import { Bell, ChevronLeft, ChevronRight, Check, Inbox } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { CATEGORIES, type CategoryId } from "@/lib/categories";
import { type Notice } from "@/lib/notices";
import { NoticeCard } from "@/components/notice-card";
import { TabBar } from "@/components/tab-bar";

const PAGE_SIZE = 10;

export function HomeClient({ notices }: { notices: Notice[] }) {
  // Empty set = no filter = every notice is shown (the default state).
  const [selected, setSelected] = React.useState<Set<CategoryId>>(new Set());
  const [page, setPage] = React.useState(1);

  const filtered = React.useMemo(() => {
    if (selected.size === 0) return notices;
    return notices.filter((n) => n.categories.some((c) => selected.has(c)));
  }, [selected, notices]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const pageItems = filtered.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  );

  const clearFilter = () => {
    setSelected(new Set());
    setPage(1);
  };

  const toggleCategory = (id: CategoryId) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
    setPage(1);
  };

  const goToPage = (p: number) => {
    setPage(p);
    if (typeof window !== "undefined") {
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col bg-background pb-20">
      {/* Sticky header + category filter */}
      <header className="sticky top-0 z-20 border-b border-border bg-background/90 backdrop-blur">
        <div className="flex items-center gap-2 px-4 pb-3 pt-4">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-sm">
            <Bell className="h-[18px] w-[18px]" />
          </div>
          <div className="min-w-0">
            <h1 className="text-base font-bold leading-tight tracking-tight text-foreground">
              NotiCE
            </h1>
            <p className="text-[11px] leading-tight text-muted-foreground">
              컴퓨터공학과 공지사항
            </p>
          </div>
        </div>

        {/* Filter chips — wrap to multiple lines so all are visible */}
        <div className="flex flex-wrap gap-2 px-4 pb-3">
          <FilterChip
            label="전체"
            active={selected.size === 0}
            onClick={clearFilter}
          />
          {CATEGORIES.map((cat) => (
            <FilterChip
              key={cat.id}
              label={cat.label}
              active={selected.has(cat.id)}
              dotClass={cat.dotClass}
              onClick={() => toggleCategory(cat.id)}
            />
          ))}
        </div>
      </header>

      {/* Notice list */}
      <main className="flex-1 px-4 py-4">
        <div className="mb-3 flex items-center justify-between px-0.5">
          <p className="text-xs text-muted-foreground">
            총{" "}
            <span className="font-semibold text-foreground">
              {filtered.length}
            </span>
            건
          </p>
          {selected.size > 0 && (
            <button
              type="button"
              onClick={clearFilter}
              className="text-xs font-medium text-primary hover:underline"
            >
              필터 초기화
            </button>
          )}
        </div>

        {pageItems.length === 0 ? (
          <EmptyState hasFilter={selected.size > 0} onReset={clearFilter} />
        ) : (
          <AnimatePresence mode="wait">
            <motion.ul
              key={`${currentPage}-${[...selected].sort().join(",")}`}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -8 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="space-y-2.5"
            >
              {pageItems.map((notice) => (
                <li key={notice.id}>
                  <NoticeCard notice={notice} />
                </li>
              ))}
            </motion.ul>
          </AnimatePresence>
        )}

        {filtered.length > 0 && (
          <Pagination
            currentPage={currentPage}
            totalPages={totalPages}
            onChange={goToPage}
          />
        )}
      </main>

      <TabBar active="home" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Filter chip                                                         */
/* ------------------------------------------------------------------ */

function FilterChip({
  label,
  active,
  dotClass,
  onClick,
}: {
  label: string;
  active: boolean;
  dotClass?: string;
  onClick: () => void;
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      whileTap={{ scale: 0.94 }}
      aria-pressed={active}
      className={cn(
        "flex shrink-0 items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-1 focus-visible:ring-offset-background",
        active
          ? "border-primary bg-primary text-primary-foreground shadow-sm"
          : "border-border bg-background text-foreground hover:border-primary/40 hover:bg-accent/60"
      )}
    >
      {active ? (
        <Check className="h-3.5 w-3.5" strokeWidth={3} />
      ) : dotClass ? (
        <span className={cn("h-2 w-2 rounded-full", dotClass)} />
      ) : null}
      {label}
    </motion.button>
  );
}

/* ------------------------------------------------------------------ */
/* Pagination                                                          */
/* ------------------------------------------------------------------ */

function Pagination({
  currentPage,
  totalPages,
  onChange,
}: {
  currentPage: number;
  totalPages: number;
  onChange: (p: number) => void;
}) {
  if (totalPages <= 1) return null;

  const items = getPageWindow(currentPage, totalPages);

  return (
    <nav
      aria-label="페이지 이동"
      className="mt-6 flex items-center justify-center gap-1"
    >
      <Button
        variant="outline"
        size="icon"
        onClick={() => onChange(currentPage - 1)}
        disabled={currentPage === 1}
        aria-label="이전 페이지"
      >
        <ChevronLeft className="h-4 w-4" />
      </Button>

      {items.map((item, i) =>
        item === "ellipsis" ? (
          <span
            key={`e${i}`}
            className="flex h-10 w-6 items-center justify-center text-sm text-muted-foreground"
            aria-hidden
          >
            …
          </span>
        ) : (
          <button
            key={item}
            type="button"
            onClick={() => onChange(item)}
            aria-current={item === currentPage ? "page" : undefined}
            className={cn(
              "h-10 min-w-10 rounded-md px-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
              item === currentPage
                ? "bg-primary text-primary-foreground shadow-sm"
                : "text-foreground hover:bg-secondary"
            )}
          >
            {item}
          </button>
        )
      )}

      <Button
        variant="outline"
        size="icon"
        onClick={() => onChange(currentPage + 1)}
        disabled={currentPage === totalPages}
        aria-label="다음 페이지"
      >
        <ChevronRight className="h-4 w-4" />
      </Button>
    </nav>
  );
}

/**
 * Compact page list around the current page:
 *   page 1  of 23 → [1, 2, …, 23]
 *   page 12 of 23 → [1, …, 11, 12, 13, …, 23]
 *   page 23 of 23 → [1, …, 22, 23]
 */
function getPageWindow(
  current: number,
  total: number
): Array<number | "ellipsis"> {
  const delta = 1;
  const left = Math.max(2, current - delta);
  const right = Math.min(total - 1, current + delta);
  const items: Array<number | "ellipsis"> = [1];

  if (left > 2) items.push("ellipsis");
  for (let i = left; i <= right; i++) items.push(i);
  if (right < total - 1) items.push("ellipsis");
  if (total > 1) items.push(total);

  return items;
}

/* ------------------------------------------------------------------ */
/* Empty state                                                         */
/* ------------------------------------------------------------------ */

function EmptyState({
  hasFilter,
  onReset,
}: {
  hasFilter: boolean;
  onReset: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-16 text-center">
      <div className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-muted">
        <Inbox className="h-7 w-7 text-muted-foreground" />
      </div>
      <p className="text-sm font-medium text-foreground">
        {hasFilter ? "해당 카테고리의 공지가 없어요" : "표시할 공지가 없어요"}
      </p>
      <p className="mt-1 text-xs text-muted-foreground">
        {hasFilter
          ? "다른 카테고리를 선택하거나 필터를 초기화해 보세요."
          : "잠시 후 다시 확인해 주세요."}
      </p>
      {hasFilter && (
        <Button variant="outline" size="sm" className="mt-4" onClick={onReset}>
          필터 초기화
        </Button>
      )}
    </div>
  );
}
