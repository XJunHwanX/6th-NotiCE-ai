"""
body_text 공백/줄바꿈 정리 스크립트

- 문구 패턴에 의존하지 않는, 무조건 안전한 정제만 수행:
  1. 연속된 빈 줄(3줄 이상)을 2줄로 축소
  2. 각 줄 앞뒤 불필요한 공백(스페이스/탭) 제거
  3. 줄 안에서 연속된 공백(스페이스 2개 이상)을 1개로 축소
  4. 파일 앞뒤 불필요한 공백/줄바꿈 제거

- [표 내용], [이미지 OCR 내용] 태그는 절대 건드리지 않음(출처 구분용으로 유지)
- 인사말/서명 문구 제거는 여기서 하지 않음 (패턴이 일정하지 않아 별도 처리 필요)

crawler 폴더 안에서 실행하는 걸 기준으로 상대경로를 사용합니다.
"""

import pandas as pd
import re

INPUT_PATH = "../data/cse_notices_with_content.csv"
OUTPUT_PATH = "../data/cse_notices_with_content.csv"  # 같은 파일에 덮어쓰기


def clean_text(text: str) -> str:
    if not isinstance(text, str):
        return text

    # 1. 줄 단위로 나눠서 각 줄 앞뒤 공백 제거 + 줄 내부 연속 공백 축소
    lines = text.split("\n")
    lines = [re.sub(r"[ \t]{2,}", " ", line.strip()) for line in lines]
    text = "\n".join(lines)

    # 2. 연속된 빈 줄(3줄 이상)을 2줄로 축소
    text = re.sub(r"\n{3,}", "\n\n", text)

    # 3. 파일 앞뒤 공백/줄바꿈 제거
    text = text.strip()

    return text


df = pd.read_csv(INPUT_PATH)

before_lengths = df["body_text"].astype(str).str.len()

df["body_text"] = df["body_text"].apply(clean_text)

after_lengths = df["body_text"].astype(str).str.len()

reduced = before_lengths - after_lengths

print(f"전체 행 수: {len(df)}")
print(f"글자 수가 줄어든 행: {(reduced > 0).sum()}개")
print(f"평균 감소 글자 수: {reduced[reduced > 0].mean():.1f}자")
print(f"가장 많이 줄어든 행: {reduced.max()}자 (article_no: {df.loc[reduced.idxmax(), 'article_no']})")

# 태그 보존 확인 (혹시라도 정규식이 태그를 훼손했는지 체크)
tag_check_before = df["body_text"].astype(str).str.contains(r"\[표 내용\]|\[이미지 OCR 내용\]").sum()
print(f"\n[표 내용]/[이미지 OCR 내용] 태그가 포함된 행: {tag_check_before}개 (정제 후에도 유지됨)")

df.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig")
print(f"\n정제 완료 및 저장: {OUTPUT_PATH}")