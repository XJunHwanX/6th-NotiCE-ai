import {
  BookOpen,
  GraduationCap,
  Microscope,
  Users,
  Wallet,
  Trophy,
  Briefcase,
  MoreHorizontal,
  type LucideIcon,
} from "lucide-react";

export type CategoryId =
  | "academic"
  | "graduation"
  | "research"
  | "activity"
  | "scholarship"
  | "contest"
  | "career"
  | "etc";

export type Category = {
  id: CategoryId;
  label: string;
  desc: string;
  icon: LucideIcon;
};

/**
 * Single source of truth for the 8 notice categories.
 * Shared by onboarding, home filter chips, and notice cards.
 * Category tags now share one unified accent color for a cleaner, calmer look
 * (previously each category had its own color, which felt busy).
 */
export const CATEGORIES: Category[] = [
  { id: "academic", label: "학사", desc: "수강신청·시험·성적", icon: BookOpen },
  {
    id: "graduation",
    label: "졸업",
    desc: "졸업요건·논문",
    icon: GraduationCap,
  },
  {
    id: "research",
    label: "대학원/연구",
    desc: "연구실·세미나",
    icon: Microscope,
  },
  { id: "activity", label: "학생활동", desc: "동아리·행사", icon: Users },
  {
    id: "scholarship",
    label: "장학/근로",
    desc: "장학금·교내근로",
    icon: Wallet,
  },
  {
    id: "contest",
    label: "대회/공모전",
    desc: "해커톤·경진대회",
    icon: Trophy,
  },
  { id: "career", label: "취업/인턴", desc: "채용·인턴십", icon: Briefcase },
  { id: "etc", label: "기타", desc: "그 외 공지", icon: MoreHorizontal },
];

const CATEGORY_MAP = new Map(CATEGORIES.map((c) => [c.id, c]));

export function getCategory(id: CategoryId): Category {
  const found = CATEGORY_MAP.get(id);
  if (!found) throw new Error(`Unknown category id: ${id}`);
  return found;
}

/**
 * Aliases for normalizing raw category strings coming from the DB.
 * Accepts our own ids, the Korean labels, and a few likely variants.
 * NOTE: once the real distinct `category` values are known, extend this map
 * so nothing silently falls back to "기타".
 */
const CATEGORY_ALIASES: Record<string, CategoryId> = {
  // ids
  academic: "academic",
  graduation: "graduation",
  research: "research",
  activity: "activity",
  scholarship: "scholarship",
  contest: "contest",
  career: "career",
  etc: "etc",
  // Korean labels
  학사: "academic",
  졸업: "graduation",
  "대학원/연구": "research",
  대학원: "research",
  연구: "research",
  학생활동: "activity",
  "장학/근로": "scholarship",
  장학: "scholarship",
  근로: "scholarship",
  "대회/공모전": "contest",
  대회: "contest",
  공모전: "contest",
  "취업/인턴": "career",
  취업: "career",
  인턴: "career",
  기타: "etc",
};

/** Map one raw DB category string to a known CategoryId (unknown → "etc"). */
export function normalizeCategory(raw: string): CategoryId {
  return CATEGORY_ALIASES[raw.trim()] ?? "etc";
}

/** Map a raw category array (nullable) to a deduped list of known ids. */
export function normalizeCategories(raw: string[] | null | undefined): CategoryId[] {
  if (!raw || raw.length === 0) return ["etc"];
  const ids = raw.map(normalizeCategory);
  return [...new Set(ids)];
}
