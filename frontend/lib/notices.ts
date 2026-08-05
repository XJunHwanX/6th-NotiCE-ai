import { normalizeCategories, type CategoryId } from "./categories";
import { getSupabase, isSupabaseConfigured } from "./supabase";

export type Notice = {
  id: string;
  title: string;
  /** Original notice link — cards open this directly. */
  url: string;
  /** A notice may belong to multiple categories. */
  categories: CategoryId[];
  publishedAt: Date | null;
  deadline: Date | null;
};

/* ------------------------------------------------------------------ */
/* Supabase                                                            */
/* ------------------------------------------------------------------ */

// Cards link straight to the original notice URL, so the body (`content`)
// is never rendered in-app and is intentionally not fetched.
const COLUMNS = "id,title,url,category,published_at,deadline";

type NoticeRow = {
  id: number | string;
  title: string;
  url: string;
  category: string[] | null;
  published_at: string | null;
  deadline: string | null;
};

function mapRow(row: NoticeRow): Notice {
  return {
    id: String(row.id),
    title: row.title,
    url: row.url,
    categories: normalizeCategories(row.category),
    publishedAt: row.published_at ? new Date(row.published_at) : null,
    deadline: row.deadline ? new Date(row.deadline) : null,
  };
}

/** All notices, newest first. Falls back to dummy data until Supabase is configured. */
export async function getNotices(): Promise<Notice[]> {
  if (!isSupabaseConfigured()) return DUMMY_NOTICES;

  const { data, error } = await getSupabase()
    .from("notices")
    .select(COLUMNS)
    .order("published_at", { ascending: false, nullsFirst: false });

  if (error) throw new Error(`공지를 불러오지 못했습니다: ${error.message}`);
  return (data ?? []).map(mapRow);
}

/* ------------------------------------------------------------------ */
/* Dummy fallback data (used only when Supabase env is not set)        */
/* ------------------------------------------------------------------ */

type Seed = {
  id: string;
  title: string;
  category: CategoryId;
  postedAgo: number;
  deadlineIn: number | null;
  content: string;
};

/** A couple of notices carry two categories to exercise multi-tag rendering. */
const MULTI: Record<string, CategoryId[]> = {
  "2026-0803": ["scholarship", "academic"],
  "2026-0806": ["career", "activity"],
};

const SEEDS: Seed[] = [
  {
    id: "2026-0801",
    title: "2026학년도 2학기 수강신청 일정 및 유의사항 안내",
    category: "academic",
    postedAgo: 0,
    deadlineIn: 0,
    content:
      "2026학년도 2학기 수강신청이 오늘 마감됩니다. 정정기간 이전에 반드시 시간표를 최종 확인하시기 바랍니다.",
  },
  {
    id: "2026-0802",
    title: "제12회 컴퓨터공학과 해커톤 'HONGIK HACK' 참가팀 모집",
    category: "contest",
    postedAgo: 1,
    deadlineIn: 2,
    content:
      "48시간 동안 자유 주제로 서비스를 개발하는 교내 해커톤입니다. 3~5인 1팀으로 신청 가능합니다.",
  },
  {
    id: "2026-0803",
    title: "2026-2학기 국가장학금 2차 신청 기간 안내",
    category: "scholarship",
    postedAgo: 2,
    deadlineIn: 5,
    content:
      "한국장학재단 국가장학금 2차 신청 기간입니다. 기간 내 미신청 시 해당 학기 지원이 불가합니다.",
  },
  {
    id: "2026-0804",
    title: "졸업논문(캡스톤디자인) 최종 발표회 및 제출 안내",
    category: "graduation",
    postedAgo: 2,
    deadlineIn: 7,
    content:
      "2026학년도 2학기 졸업예정자 대상 캡스톤디자인 최종 발표회를 진행합니다. 미제출 시 졸업 사정에서 제외됩니다.",
  },
  {
    id: "2026-0805",
    title: "인공지능연구실(AI Lab) 2026년 하반기 학부연구생 모집",
    category: "research",
    postedAgo: 3,
    deadlineIn: 3,
    content:
      "머신러닝·컴퓨터비전 분야 학부연구생을 모집합니다. 우수 연구생은 대학원 진학 시 우대합니다.",
  },
  {
    id: "2026-0806",
    title: "삼성전자 DS부문 2026 하계 인턴십 채용설명회 개최",
    category: "career",
    postedAgo: 3,
    deadlineIn: 1,
    content:
      "삼성전자 DS부문 현직자가 참여하는 채용설명회를 개최합니다. 사전 신청자에 한해 1:1 이력서 첨삭이 제공됩니다.",
  },
  {
    id: "2026-0807",
    title: "컴퓨터공학과 학생회 주최 '전공 멘토링 데이' 신청 안내",
    category: "activity",
    postedAgo: 4,
    deadlineIn: 6,
    content:
      "고학년 선배와 저학년 후배를 연결하는 전공 멘토링 프로그램입니다. 참여자 전원에게 소정의 다과가 제공됩니다.",
  },
  {
    id: "2026-0808",
    title: "2학기 교내 근로장학생(행정·전산) 모집 공고",
    category: "scholarship",
    postedAgo: 4,
    deadlineIn: 4,
    content:
      "학과 사무실 및 전산실에서 근무할 교내 근로장학생을 모집합니다. 재학생이라면 누구나 지원 가능합니다.",
  },
  {
    id: "2026-0809",
    title: "SW 역량 강화를 위한 알고리즘 스터디 그룹 모집",
    category: "activity",
    postedAgo: 5,
    deadlineIn: 9,
    content:
      "코딩테스트와 알고리즘 대비 스터디 그룹을 운영합니다. 초급/중급 트랙으로 나누어 진행합니다.",
  },
  {
    id: "2026-0810",
    title: "2026학년도 2학기 전공 교과목 폐강 및 분반 조정 안내",
    category: "academic",
    postedAgo: 5,
    deadlineIn: null,
    content:
      "수강신청 인원 미달로 일부 전공선택 과목이 폐강되었습니다. 해당 과목 수강생은 정정기간에 대체 과목을 신청하세요.",
  },
  {
    id: "2026-0811",
    title: "네이버 부스트캠프 웹·모바일 2026 지원 안내",
    category: "career",
    postedAgo: 6,
    deadlineIn: 14,
    content:
      "네이버 커넥트재단이 운영하는 부스트캠프 지원 접수가 시작되었습니다. 수료 시 채용 연계 혜택이 있습니다.",
  },
  {
    id: "2026-0812",
    title: "대학원 입학설명회 및 연구실 투어 프로그램 안내",
    category: "research",
    postedAgo: 6,
    deadlineIn: 30,
    content:
      "대학원 진학에 관심 있는 학부생을 위한 입학설명회를 개최합니다. 재학생 Q&A와 연구실 투어가 포함됩니다.",
  },
  {
    id: "2026-0813",
    title: "제8회 전국 대학생 프로그래밍 경진대회(UCPC) 예선 안내",
    category: "contest",
    postedAgo: 7,
    deadlineIn: 7,
    content:
      "전국 대학생 대상 프로그래밍 경진대회 예선이 온라인으로 진행됩니다. 본선 진출팀에는 참가비가 지원됩니다.",
  },
  {
    id: "2026-0814",
    title: "졸업요건 자가진단 시스템 오픈 및 확인 요청",
    category: "graduation",
    postedAgo: 8,
    deadlineIn: null,
    content:
      "학사관리시스템에서 졸업요건 자가진단 기능을 이용할 수 있습니다. 부족한 요건이 없도록 미리 준비하세요.",
  },
  {
    id: "2026-0815",
    title: "2026 컴퓨터공학과 신입생 환영회 및 학과 소개의 밤",
    category: "activity",
    postedAgo: 9,
    deadlineIn: -3,
    content:
      "신입생과 재학생이 함께하는 학과 행사입니다. (신청은 마감되었습니다.)",
  },
  {
    id: "2026-0816",
    title: "카카오 2026 겨울 인턴십(테크 트랙) 채용 공고",
    category: "career",
    postedAgo: 10,
    deadlineIn: 12,
    content:
      "카카오 테크 트랙 겨울 인턴십 채용이 진행됩니다. 코딩테스트와 기술면접으로 선발합니다.",
  },
  {
    id: "2026-0817",
    title: "2026-2학기 성적 우수 장학생 선발 결과 발표",
    category: "scholarship",
    postedAgo: 11,
    deadlineIn: null,
    content:
      "직전 학기 성적을 기준으로 한 성적 우수 장학생 선발이 완료되었습니다. 장학금은 등록금 고지서에 반영됩니다.",
  },
  {
    id: "2026-0818",
    title: "컴퓨터공학과 오픈소스 컨트리뷰션 아카데미 모집",
    category: "contest",
    postedAgo: 12,
    deadlineIn: 20,
    content:
      "실제 오픈소스 프로젝트에 기여하며 협업 경험을 쌓는 아카데미입니다. 이슈 해결부터 PR 머지까지 경험할 수 있습니다.",
  },
  {
    id: "2026-0819",
    title: "학사경고 대상자 대상 학습 상담 프로그램 안내",
    category: "academic",
    postedAgo: 13,
    deadlineIn: -1,
    content:
      "학습에 어려움을 겪는 학생을 위한 1:1 상담 프로그램입니다. (이번 학기 신청은 마감되었습니다.)",
  },
  {
    id: "2026-0820",
    title: "데이터베이스연구실 대학원 신입생(석·박사) 모집",
    category: "research",
    postedAgo: 14,
    deadlineIn: 25,
    content:
      "대규모 데이터 처리와 분산 시스템을 연구하는 연구실에서 대학원 신입생을 모집합니다.",
  },
  {
    id: "2026-0821",
    title: "졸업앨범 촬영 일정 및 개별 촬영 예약 안내",
    category: "graduation",
    postedAgo: 15,
    deadlineIn: -7,
    content:
      "2026학년도 졸업예정자 졸업앨범 촬영 일정입니다. (예약이 마감되었습니다.)",
  },
  {
    id: "2026-0822",
    title: "교내 무선랜(Wi-Fi) 및 학과 실습실 PC 점검 안내",
    category: "etc",
    postedAgo: 16,
    deadlineIn: null,
    content:
      "네트워크 안정화를 위한 정기 점검이 예정되어 있습니다. 점검 시간 동안 접속이 제한될 수 있습니다.",
  },
  {
    id: "2026-0823",
    title: "분실물 보관 안내 및 미수령 물품 처리 공지",
    category: "etc",
    postedAgo: 18,
    deadlineIn: null,
    content:
      "학과 건물에서 습득된 분실물을 사무실에서 보관 중입니다. 미수령 물품은 절차에 따라 처리됩니다.",
  },
];

const DAY_MS = 86_400_000;

const DUMMY_NOTICES: Notice[] = SEEDS.map((s) => {
  const now = Date.now();
  return {
    id: s.id,
    title: s.title,
    url: "#",
    categories: MULTI[s.id] ?? [s.category],
    publishedAt: new Date(now - s.postedAgo * DAY_MS),
    deadline: s.deadlineIn === null ? null : new Date(now + s.deadlineIn * DAY_MS),
  };
}).sort(
  (a, b) => (b.publishedAt?.getTime() ?? 0) - (a.publishedAt?.getTime() ?? 0)
);
