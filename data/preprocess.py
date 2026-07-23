import pandas as pd

# CSV 불러오기
cse_df = pd.read_csv("data/cse_notices.csv", encoding="utf-8-sig")
total_df = pd.read_csv("data/total_notices.csv", encoding="utf-8-sig")

print("=" * 50)
print("[컴공과 공지] 기본 현황")
print(f"전체 행 수: {len(cse_df)}개")

# 중복 확인 (article_no 기준)
cse_duplicates = cse_df[cse_df.duplicated(subset="article_no", keep=False)]
print(f"중복 행 수: {len(cse_duplicates)}개")

# 중복 제거
cse_df = cse_df.drop_duplicates(subset="article_no")
print(f"중복 제거 후 행 수: {len(cse_df)}개")

# 결측치 확인
print("\n결측치 현황:")
print(cse_df.isnull().sum())

print()
print("=" * 50)
print("[전체 공지] 기본 현황")
print(f"전체 행 수: {len(total_df)}개")

# 중복 확인
total_duplicates = total_df[total_df.duplicated(subset="article_no", keep=False)]
print(f"중복 행 수: {len(total_duplicates)}개")

# 중복 제거
total_df = total_df.drop_duplicates(subset="article_no")
print(f"중복 제거 후 행 수: {len(total_df)}개")

# 결측치 확인
print("\n결측치 현황:")
print(total_df.isnull().sum())

# 카테고리 종류 확인 (전체 공지만)
print()
print("=" * 50)
print("[전체 공지] 카테고리별 개수")
print(total_df["category"].value_counts(dropna=False))

# 전처리 완료된 CSV 저장
cse_df.to_csv("data/cse_notices.csv", index=False, encoding="utf-8-sig")
total_df.to_csv("data/total_notices.csv", index=False, encoding="utf-8-sig")
print()
print("전처리 완료된 CSV 저장 완료")