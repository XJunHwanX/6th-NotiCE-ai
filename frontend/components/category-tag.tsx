import { getCategory, type CategoryId } from "@/lib/categories";
import { cn } from "@/lib/utils";

export function CategoryTag({
  category,
  className,
}: {
  category: CategoryId;
  className?: string;
}) {
  const c = getCategory(category);
  return (
    <span
      className={cn(
        // 모든 카테고리를 하나의 accent 색으로 통일 (이전엔 카테고리별로 색이 달라 번잡했음)
        "inline-flex shrink-0 items-center rounded-md bg-accent px-2 py-0.5 text-xs font-semibold text-accent-foreground",
        className
      )}
    >
      {c.label}
    </span>
  );
}
