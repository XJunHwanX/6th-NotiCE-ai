"""
date 컬럼 형식 변환 스크립트
2026.07.06 (점 구분) -> 2026-07-06 (하이픈 구분, Postgres 표준 형식)

crawler 폴더 안에서 실행하는 다른 스크립트들과 통일감을 맞추기 위해
상대경로(../data/...)를 사용합니다. 루트 폴더에서 실행하고 싶다면
INPUT_PATH, OUTPUT_PATH를 'data/...'로 바꿔서 쓰면 됩니다.
"""

import pandas as pd

INPUT_PATH = "../data/cse_notices_with_content.csv"
OUTPUT_PATH = "../data/cse_notices_with_content.csv"  # 같은 파일에 덮어쓰기

df = pd.read_csv(INPUT_PATH)

before_sample = df["date"].head(3).tolist()

# 점(.)을 하이픈(-)으로 변환
df["date"] = df["date"].astype(str).str.strip().str.replace(".", "-", regex=False)

# 혹시 끝에 하이픈이 남는 경우(예: "2026.07.06." 처럼 끝에 점이 있던 경우) 정리
df["date"] = df["date"].str.rstrip("-")

after_sample = df["date"].head(3).tolist()

# 변환이 실제 날짜 형식(YYYY-MM-DD)인지 검증
invalid = df[~df["date"].str.match(r"^\d{4}-\d{2}-\d{2}$")]

print(f"변환 전 샘플: {before_sample}")
print(f"변환 후 샘플: {after_sample}")
print(f"전체 행 수: {len(df)}")
print(f"형식이 안 맞는 행 수: {len(invalid)}")

if len(invalid) > 0:
    print("\n[경고] 아래 행들은 YYYY-MM-DD 형식이 아닙니다. 직접 확인이 필요합니다:")
    print(invalid[["article_no", "title", "date"]])
else:
    df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
    print(f"\n변환 완료 및 저장: {OUTPUT_PATH}")