import Link from "next/link";
import { Home, MessageCircle, Settings, type LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type TabId = "home" | "chat" | "settings";

type Tab = {
  id: TabId;
  label: string;
  icon: LucideIcon;
  href: string | null; // null = not implemented yet (placeholder)
};

const TABS: Tab[] = [
  { id: "home", label: "홈", icon: Home, href: "/" },
  { id: "chat", label: "챗봇", icon: MessageCircle, href: null },
  { id: "settings", label: "설정", icon: Settings, href: null },
];

export function TabBar({ active = "home" }: { active?: TabId }) {
  return (
    <nav className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/90 backdrop-blur">
      <ul className="mx-auto flex max-w-md">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.id === active;

          const inner = (
            <span
              className={cn(
                "flex flex-col items-center gap-1 py-2.5 text-[11px] font-medium transition-colors",
                isActive
                  ? "text-primary"
                  : "text-muted-foreground group-hover:text-foreground"
              )}
            >
              <Icon
                className="h-5 w-5"
                strokeWidth={isActive ? 2.5 : 2}
                aria-hidden
              />
              {tab.label}
            </span>
          );

          return (
            <li key={tab.id} className="flex-1">
              {tab.href ? (
                <Link
                  href={tab.href}
                  aria-current={isActive ? "page" : undefined}
                  className="group flex w-full items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  {inner}
                </Link>
              ) : (
                <button
                  type="button"
                  disabled
                  title="준비 중이에요"
                  className="group flex w-full cursor-not-allowed items-center justify-center opacity-50"
                >
                  {inner}
                </button>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
