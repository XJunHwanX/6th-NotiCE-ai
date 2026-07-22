"""
병합 스크립트: 크롤링 CSV(cse_notices_with_content.csv) + 라벨링 스프레드시트(구글시트 export)

- article_no 기준으로 병합
- 라벨 CSV의 E열(최종 라벨) 값을 category로 사용
- "취업인턴" 오타는 "취업/인턴"으로 자동 통일
- 라벨이 없는 공지(크롤링 CSV에는 있지만 라벨 CSV에는 없는 경우)는 category를 NULL로 둠
- 라벨 CSV 하단의 통계용 빈 행(article_no 없음)은 자동 제외
- 결과물: article_no, title, url, published_at, category (DB insert용 최소 컬럼)
  + body_text 등 원본 컬럼도 참고용으로 같이 남겨둠 (필요시 C가 활용 가능)

사용법 (crawler 폴더 안에서 실행):
    python merge_labels.py
"""

import pandas as pd

CRAWLED_PATH = "../data/cse_notices_with_content.csv"
LABEL_PATH = "../data/cse_notices_labels.csv"  # 구글시트에서 export한 라벨 CSV를 이 경로에 두고 실행
OUTPUT_PATH = "../data/cse_notices_final.csv"

# 라벨 CSV의 최종 라벨 컬럼명 (구글시트 export 시 자동 생성된 이름, 필요시 수정)
LABEL_COLUMN = "Unnamed: 4"

# 오타/표기 통일용 매핑
CATEGORY_FIX_MAP = {
    "취업인턴": "취업/인턴",
    "장학": "장학/근로",       # F,G,H열처럼 "장학"으로만 적힌 경우 대비 (혹시 몰라 추가)
    "대회·공모전": "대회/공모전",  # 가운뎃점 표기 통일
}

# ---- 1. 크롤링 CSV 로드 ----
crawled = pd.read_csv(CRAWLED_PATH)
print(f"크롤링 CSV: {len(crawled)}행")

# ---- 2. 라벨 CSV 로드 ----
labels = pd.read_csv(LABEL_PATH)

# article_no가 없는 행(통계용 빈 행) 제거
labels = labels[labels["article_no"].notna()].copy()
print(f"라벨 CSV (통계행 제외): {len(labels)}행")

# article_no 타입 통일 (둘 다 int로)
crawled["article_no"] = crawled["article_no"].astype(int)
labels["article_no"] = labels["article_no"].astype(int)

# 카테고리 컬럼 추출 + 오타/표기 통일
labels["category"] = labels[LABEL_COLUMN].replace(CATEGORY_FIX_MAP)

# ---- 3. 병합 (left join: 크롤링 CSV 기준, 라벨 없으면 NaN) ----
merged = crawled.merge(
    labels[["article_no", "category"]],
    on="article_no",
    how="left"
)

# ---- 4. date -> published_at 컬럼명 정리 (이미 하이픈 형식으로 변환되어 있다고 가정) ----
if "date" in merged.columns:
    merged = merged.rename(columns={"date": "published_at"})

# ---- 5. 결과 확인 ----
no_label = merged[merged["category"].isna()]
print(f"\n최종 병합 결과: {len(merged)}행")
print(f"category가 없는(라벨 안 된) 공지: {len(no_label)}개")
if len(no_label) > 0:
    print(no_label[["article_no", "title"]].to_string())

print("\n최종 카테고리 분포:")
print(merged["category"].value_counts(dropna=False))

# ---- 6. 저장 ----
merged.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
print(f"\n저장 완료: {OUTPUT_PATH}")