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
        "inline-flex shrink-0 items-center rounded-md px-2 py-0.5 text-xs font-semibold",
        c.tagClass,
        className
      )}
    >
      {c.label}
    </span>
  );
}
